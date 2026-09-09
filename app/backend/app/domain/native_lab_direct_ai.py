"""Native C++ -> AI laboratory synthesis bridge.

The existing document reader still extracts structured laboratory rows first. Those rows
are then passed to ``medicore_lab_ai``. The native C++ module rebuilds/validates the row
contract and performs the HTTPS request itself, so the second clinical AI hop no longer
needs the Python OpenAI SDK when native HTTP support is available.

If the optional native HTTP transport was not compiled (or the provider call fails), the
existing Python clinical service remains the resilience fallback. This keeps deployments
working while the C++ transport is rolled out progressively.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from functools import lru_cache
from typing import Any, Mapping, Sequence

from app.core.config import get_settings
from app.domain.openai_lab_clinical_service import (
    OpenAILabClinicalError,
    synthesize_lab_clinical_assessment as _python_clinical_synthesis,
)

AI_DISPATCH_CONTRACT = "medicore-lab-ai-dispatch-v1"
_DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"


@lru_cache(maxsize=1)
def _load_native_ai_module() -> Any | None:
    try:
        return importlib.import_module("medicore_lab_ai")
    except (ImportError, OSError):
        return None


def native_lab_direct_ai_available() -> bool:
    module = _load_native_ai_module()
    return bool(
        module is not None
        and getattr(module, "AI_DISPATCH_VERSION", None) == AI_DISPATCH_CONTRACT
        and bool(getattr(module, "HTTP_AVAILABLE", False))
        and callable(getattr(module, "dispatch_all_rows", None))
    )


def _extract_responses_output_text(payload: Mapping[str, Any]) -> str:
    """Extract the assistant JSON text from a raw Responses API HTTP payload."""
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    pieces: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                if part.get("type") != "output_text":
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    pieces.append(text)
    return "".join(pieces).strip()


def _validate_assessment_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpenAILabClinicalError("Native C++ AI yanıtı beklenen nesne yapısında değil.")

    required = {
        "headline",
        "overview",
        "priority_findings",
        "systems",
        "reassuring_findings",
        "priority_actions",
        "limitations",
        "narrative_tr",
    }
    missing = sorted(required.difference(value))
    if missing:
        raise OpenAILabClinicalError(
            "Native C++ AI yanıtında zorunlu alanlar eksik: " + ", ".join(missing)
        )
    return dict(value)


async def _native_synthesis(
    *,
    rows: Sequence[Mapping[str, Any]],
    patient_age: int | None,
    patient_sex: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    module = _load_native_ai_module()
    if module is None:
        raise OpenAILabClinicalError("MediCore native C++ AI dispatch modülü yüklü değil.")
    if getattr(module, "AI_DISPATCH_VERSION", None) != AI_DISPATCH_CONTRACT:
        raise OpenAILabClinicalError("MediCore native C++ AI dispatch contract sürümü uyumsuz.")
    if not bool(getattr(module, "HTTP_AVAILABLE", False)):
        raise OpenAILabClinicalError("MediCore native C++ AI HTTP transport derlenmemiş.")
    if not settings.openai_api_key:
        raise OpenAILabClinicalError("OPENAI_API_KEY yapılandırılmamış.")

    model = (settings.openai_lab_clinical_model or settings.openai_lab_model or "").strip()
    if not model:
        raise OpenAILabClinicalError("Laboratuvar klinik AI modeli yapılandırılmamış.")

    payload_rows = [dict(row) for row in rows]
    if not payload_rows:
        raise OpenAILabClinicalError("AI'ya gönderilecek laboratuvar sonucu bulunmuyor.")

    try:
        native_result = await asyncio.to_thread(
            module.dispatch_all_rows,
            payload_rows,
            patient_age,
            patient_sex or "",
            settings.openai_api_key,
            model,
            _DEFAULT_ENDPOINT,
            float(settings.ai_call_timeout_seconds),
            3200,
        )
    except Exception as exc:
        raise OpenAILabClinicalError(f"Native C++ laboratuvar AI isteği başarısız: {exc}") from exc

    if not isinstance(native_result, Mapping):
        raise OpenAILabClinicalError("Native C++ AI transport geçersiz yanıt döndürdü.")
    if native_result.get("contract_version") != AI_DISPATCH_CONTRACT:
        raise OpenAILabClinicalError("Native C++ AI yanıt contract sürümü uyumsuz.")

    response_body = native_result.get("response_body")
    if not isinstance(response_body, str) or not response_body.strip():
        raise OpenAILabClinicalError("Native C++ AI transport boş sağlayıcı yanıtı döndürdü.")

    try:
        provider_payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise OpenAILabClinicalError("Native C++ AI sağlayıcı yanıtı geçerli JSON değil.") from exc
    if not isinstance(provider_payload, Mapping):
        raise OpenAILabClinicalError("Native C++ AI sağlayıcı yanıtı nesne değil.")

    output_text = _extract_responses_output_text(provider_payload)
    if not output_text:
        raise OpenAILabClinicalError("Native C++ AI sağlayıcı yanıtında çıktı metni bulunamadı.")

    try:
        assessment = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise OpenAILabClinicalError("Native C++ AI klinik çıktısı geçerli JSON değil.") from exc

    result = _validate_assessment_shape(assessment)
    result["model"] = str(native_result.get("model") or model)
    result["synthesis_source"] = "native_cpp_direct_ai"
    return result


async def synthesize_lab_clinical_assessment_native(
    *,
    rows: Sequence[Mapping[str, Any]],
    derived_metrics: Sequence[Mapping[str, Any]],
    patient_age: int | None,
    patient_sex: str | None,
) -> dict[str, Any]:
    """Prefer C++ direct AI dispatch and preserve the previous service as fallback."""
    if native_lab_direct_ai_available():
        try:
            return await _native_synthesis(
                rows=rows,
                patient_age=patient_age,
                patient_sex=patient_sex,
            )
        except OpenAILabClinicalError:
            # Provider/network/build failures must not make the laboratory endpoint
            # unusable. The established Python service keeps the same safety schema.
            pass

    return await _python_clinical_synthesis(
        rows=rows,
        derived_metrics=derived_metrics,
        patient_age=patient_age,
        patient_sex=patient_sex,
    )
