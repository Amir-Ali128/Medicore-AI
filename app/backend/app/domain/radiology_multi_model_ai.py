"""Multi-provider medical-image review and conservative consensus synthesis.

The ensemble is decision support only. Providers independently inspect the same
image and return structured visual observations plus *candidate* differentials.
MediCore groups overlapping candidates and exposes agreement/disagreement; it
never converts model agreement into an autonomous final diagnosis.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.core.config import get_settings
from app.domain.report_document_image_ai import (
    RadiologyMediaReview,
    _detected_modality,
    _document_kind,
    _extract_json,
    _medical_image_guidance,
    _separate_visual_observations,
    _string_list,
    normalize_body_part,
    normalize_image_modality,
    review_radiology_media,
)

ENSEMBLE_VERSION = "radiology-multi-model-v1"


@dataclass(frozen=True)
class CandidateCondition:
    label: str
    support: str
    confidence: str


@dataclass(frozen=True)
class ProviderImageOpinion:
    provider: str
    model: str
    document_kind: str
    detected_modality: str
    detected_body_part: str
    summary: str
    observations: tuple[str, ...]
    candidate_conditions: tuple[CandidateCondition, ...]
    critical_flags: tuple[str, ...]
    limitations: tuple[str, ...]


def _clean(value: object, limit: int = 1200) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_like = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9çğıöşü]+", " ", ascii_like).strip()


def _condition_list(value: object) -> tuple[CandidateCondition, ...]:
    if not isinstance(value, list):
        return ()
    items: list[CandidateCondition] = []
    for raw in value[:8]:
        if isinstance(raw, str):
            label = _clean(raw, 180)
            support = ""
            confidence = "unspecified"
        elif isinstance(raw, dict):
            label = _clean(raw.get("label"), 180)
            support = _clean(raw.get("support"), 500)
            confidence = _clean(raw.get("confidence"), 40).lower() or "unspecified"
        else:
            continue
        if not label:
            continue
        if confidence not in {"low", "moderate", "high", "unspecified"}:
            confidence = "unspecified"
        items.append(CandidateCondition(label=label, support=support, confidence=confidence))
    return tuple(items)


def _provider_prompt(modality: str | None, body_part: str | None) -> str:
    normalized_modality = normalize_image_modality(modality) or "AUTO"
    normalized_body_part = normalize_body_part(body_part)
    guidance = _medical_image_guidance(normalized_modality, normalized_body_part)
    region = normalized_body_part or "OTHER"
    return f"""
Bu tıbbi görüntüyü bağımsız ikinci okuyucu olarak değerlendir.
İstenen modalite: {normalized_modality}. İstenen/çıkarılan bölge: {region}.

{guidance}

Ek kurallar:
- Önce bunun REPORT_DOCUMENT mı MEDICAL_IMAGE mı olduğunu ayır.
- MEDICAL_IMAGE ise doğrudan görülen anomalileri/gözlemleri yaz ve bunlardan desteklenen
  en fazla 5 *ön tanı/diferansiyel adayı* üret. Bunlar kesin tanı değildir.
- candidate_conditions içinde yalnızca görüntü bulgusuyla makul biçimde desteklenen adayları ver.
  Her aday için kısa Türkçe canonical label, onu destekleyen görsel bulgu ve low/moderate/high
  nitel güven düzeyi yaz. Yüzde olasılık verme.
- Kritik olabilecek bir görsel bulgu varsa critical_flags içine kısa bir hekim/radyolog
  doğrulama uyarısı yaz. Yoksa boş liste kullan.
- Tek ekran görüntüsünden CT/MR serisinin tamamı hakkında sonuç çıkarma. Tek kesit/tek kare ise
  bunu limitation olarak belirt.
- Rapor sayfasıysa yeni tanı üretme; yalnızca görülen metni özetle.
- Doğrudan kimlik bilgilerini hiçbir alana yazma.
- Tedavi, ilaç veya otomatik tetkik istemi üretme.

Yalnızca JSON döndür:
{{
  "document_kind": "REPORT_DOCUMENT | MEDICAL_IMAGE | OTHER",
  "detected_modality": "XRAY | ULTRASOUND | CT | MRI | MAMMOGRAPHY | DEXA | PET_CT | NUCLEAR_MEDICINE | ENDOSCOPY | PATHOLOGY | OTHER | UNKNOWN",
  "detected_body_part": "ABDOMEN | CHEST | HEAD | NECK | PELVIS | SPINE | UPPER_EXTREMITY | LOWER_EXTREMITY | BREAST | THYROID | URINARY | OBSTETRIC | OTHER",
  "summary": "1-3 cümlelik klinik görsel sentez",
  "observations": ["en fazla 10 doğrudan görsel gözlem"],
  "candidate_conditions": [
    {{"label":"kısa ön tanı/diferansiyel adı","support":"görüntüdeki destek","confidence":"low | moderate | high"}}
  ],
  "critical_flags": ["varsa acil hekim/radyolog doğrulaması gerektiren görsel sinyal"],
  "limitations": ["en fazla 8 sınırlama"]
}}
""".strip()


def _opinion_from_payload(provider: str, model: str, payload: dict[str, Any]) -> ProviderImageOpinion:
    observations = tuple(_string_list(payload.get("observations"), limit=10, item_limit=1000))
    limitations = tuple(_string_list(payload.get("limitations"), limit=8, item_limit=1000))
    observations_list, limitations_list = _separate_visual_observations(list(observations), list(limitations))
    return ProviderImageOpinion(
        provider=provider,
        model=model,
        document_kind=_document_kind(payload.get("document_kind")),
        detected_modality=_detected_modality(payload.get("detected_modality")),
        detected_body_part=normalize_body_part(_clean(payload.get("detected_body_part"), 80)) or "OTHER",
        summary=_clean(payload.get("summary"), 1800),
        observations=tuple(observations_list),
        candidate_conditions=_condition_list(payload.get("candidate_conditions")),
        critical_flags=tuple(_string_list(payload.get("critical_flags"), limit=8, item_limit=500)),
        limitations=tuple(limitations_list),
    )


def _primary_to_opinion(review: RadiologyMediaReview) -> ProviderImageOpinion:
    return ProviderImageOpinion(
        provider="anthropic",
        model=review.model,
        document_kind=review.document_kind,
        detected_modality=review.detected_modality,
        detected_body_part=review.detected_body_part,
        summary=review.summary,
        observations=tuple(review.observations),
        candidate_conditions=(),
        critical_flags=(),
        limitations=tuple(review.limitations),
    )


def _openai_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    texts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for block in item.get("content") or []:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return "\n".join(texts)


async def _openai_opinion(content: bytes, media_type: str, modality: str, body_part: str | None) -> ProviderImageOpinion | None:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_vision_model:
        return None
    data_url = f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"
    payload = {
        "model": settings.openai_vision_model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _provider_prompt(modality, body_part)},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        "max_output_tokens": 2400,
    }
    timeout = httpx.Timeout(settings.radiology_multi_model_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    text = _openai_output_text(data)
    if not text:
        raise ValueError("OpenAI görüntü yanıtı metin içermiyor.")
    return _opinion_from_payload("openai", settings.openai_vision_model, _extract_json(text))


async def _gemini_opinion(content: bytes, media_type: str, modality: str, body_part: str | None) -> ProviderImageOpinion | None:
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_vision_model:
        return None
    encoded = base64.b64encode(content).decode("ascii")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _provider_prompt(modality, body_part)},
                    {"inline_data": {"mime_type": media_type, "data": encoded}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 2400},
    }
    model = settings.gemini_vision_model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    timeout = httpx.Timeout(settings.radiology_multi_model_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers={"x-goog-api-key": settings.gemini_api_key}, json=payload)
        response.raise_for_status()
        data = response.json()
    texts: list[str] = []
    for candidate in data.get("candidates") or []:
        content_node = candidate.get("content") if isinstance(candidate, dict) else None
        for part in (content_node or {}).get("parts") or []:
            text = part.get("text") if isinstance(part, dict) else None
            if isinstance(text, str) and text.strip():
                texts.append(text)
    if not texts:
        raise ValueError("Gemini görüntü yanıtı metin içermiyor.")
    return _opinion_from_payload("gemini", model, _extract_json("\n".join(texts)))


async def _fourth_opinion(content: bytes, media_type: str, modality: str, body_part: str | None) -> ProviderImageOpinion | None:
    settings = get_settings()
    if not (
        settings.radiology_fourth_api_key
        and settings.radiology_fourth_base_url
        and settings.radiology_fourth_model
    ):
        return None
    data_url = f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"
    payload = {
        "model": settings.radiology_fourth_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _provider_prompt(modality, body_part)},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 2400,
        "temperature": 0,
    }
    url = settings.radiology_fourth_base_url.rstrip("/") + "/chat/completions"
    timeout = httpx.Timeout(settings.radiology_multi_model_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.radiology_fourth_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    message = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    if isinstance(message, list):
        text = "\n".join(
            str(item.get("text") or "") for item in message if isinstance(item, dict)
        )
    else:
        text = str(message or "")
    if not text.strip():
        raise ValueError("Dördüncü görüntü sağlayıcısı metin yanıtı döndürmedi.")
    return _opinion_from_payload("fourth_openai_compatible", settings.radiology_fourth_model, _extract_json(text))


def _similar_condition(left: str, right: str) -> bool:
    a = _fold(left)
    b = _fold(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    if SequenceMatcher(None, a, b).ratio() >= 0.72:
        return True
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    shared = a_tokens & b_tokens
    return bool(shared) and len(shared) / max(1, min(len(a_tokens), len(b_tokens))) >= 0.6


def _group_conditions(opinions: list[ProviderImageOpinion]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: list[dict[str, Any]] = []
    for opinion in opinions:
        for condition in opinion.candidate_conditions:
            group = next(
                (item for item in groups if _similar_condition(item["label"], condition.label)),
                None,
            )
            if group is None:
                group = {
                    "label": condition.label,
                    "providers": [],
                    "supports": [],
                    "confidences": [],
                }
                groups.append(group)
            if opinion.provider not in group["providers"]:
                group["providers"].append(opinion.provider)
            if condition.support:
                group["supports"].append(condition.support)
            group["confidences"].append(condition.confidence)

    provider_count = len(opinions)
    consensus: list[dict[str, Any]] = []
    solo: list[dict[str, Any]] = []
    for group in groups:
        support_count = len(group["providers"])
        item = {
            "label": group["label"],
            "supporting_provider_count": support_count,
            "total_provider_count": provider_count,
            "supporting_providers": group["providers"],
            "supporting_observations": group["supports"][:4],
            "provider_confidences": group["confidences"][:4],
            "agreement_strength": (
                "strong" if support_count >= 3 else "moderate" if support_count == 2 else "single_model"
            ),
        }
        if provider_count >= 2 and support_count >= 2:
            consensus.append(item)
        else:
            solo.append(item)
    consensus.sort(key=lambda item: (-int(item["supporting_provider_count"]), item["label"]))
    return consensus[:8], solo[:8]


def _merge_text_lists(opinions: list[ProviderImageOpinion], field: str, limit: int) -> list[str]:
    merged: list[str] = []
    folded: list[str] = []
    for opinion in opinions:
        for value in getattr(opinion, field):
            candidate = _fold(value)
            if not candidate:
                continue
            if any(SequenceMatcher(None, candidate, existing).ratio() >= 0.82 for existing in folded):
                continue
            merged.append(value)
            folded.append(candidate)
            if len(merged) >= limit:
                return merged
    return merged


def _majority(values: list[str], fallback: str) -> str:
    counts: dict[str, int] = {}
    for value in values:
        if not value or value in {"UNKNOWN", "OTHER"}:
            continue
        counts[value] = counts.get(value, 0) + 1
    return max(counts, key=counts.get) if counts else fallback


def _review_from_opinion(opinion: ProviderImageOpinion) -> RadiologyMediaReview:
    return RadiologyMediaReview(
        summary=opinion.summary or "Görüntü çoklu-model ön incelemesine alındı; hekim doğrulaması gerekir.",
        observations=list(opinion.observations),
        limitations=list(opinion.limitations),
        visible_text="",
        model=f"{opinion.provider}:{opinion.model}",
        detected_modality=opinion.detected_modality,
        detected_body_part=opinion.detected_body_part,
        document_kind=opinion.document_kind,
        report_type="UNKNOWN",
        result_text="",
        result_items=(),
        key_findings=(),
        recommendations=(),
        comparison_text="",
    )


def _consensus_summary(base: str, consensus: list[dict[str, Any]], provider_count: int) -> str:
    if not consensus:
        return base
    labels = ", ".join(
        f"{item['label']} ({item['supporting_provider_count']}/{provider_count} model)"
        for item in consensus[:3]
    )
    prefix = f"Çoklu-model ön değerlendirmesinde ortak adaylar: {labels}."
    suffix = " Bu çıktı kesin tanı değildir; görüntü ve klinik bağlam hekim/radyolog tarafından doğrulanmalıdır."
    return f"{prefix} {base}{suffix}"[:1800]


async def review_radiology_media_ensemble(
    *,
    content: bytes,
    media_type: str,
    modality: str,
    body_part: str | None = None,
) -> tuple[RadiologyMediaReview | None, dict[str, Any]]:
    """Run available providers independently and synthesize conservative agreement metadata."""

    settings = get_settings()
    provider_errors: dict[str, str] = {}
    primary: RadiologyMediaReview | None = None
    try:
        primary = await review_radiology_media(
            content=content,
            media_type=media_type,
            modality=modality,
            body_part=body_part,
        )
    except Exception as exc:  # provider isolation is intentional
        provider_errors["anthropic"] = _clean(exc, 500)

    # Preserve the high-fidelity document extraction path. Multi-model consensus is
    # primarily for actual medical images, not for re-interpreting written reports.
    if primary is not None and primary.document_kind == "REPORT_DOCUMENT":
        return primary, {
            "ensemble_version": ENSEMBLE_VERSION,
            "ensemble_mode": "document_primary_only",
            "providers_succeeded": ["anthropic"],
            "providers_failed": provider_errors,
            "provider_count": 1,
            "consensus_differential": [],
            "single_model_differential": [],
            "physician_review_required": True,
            "not_diagnostic": True,
        }

    if not settings.radiology_multi_model_enabled:
        return primary, {
            "ensemble_version": ENSEMBLE_VERSION,
            "ensemble_mode": "disabled",
            "providers_succeeded": ["anthropic"] if primary else [],
            "providers_failed": provider_errors,
            "provider_count": 1 if primary else 0,
            "physician_review_required": True,
            "not_diagnostic": True,
        }

    tasks: list[tuple[str, Any]] = []
    if settings.openai_api_key:
        tasks.append(("openai", _openai_opinion(content, media_type, modality, body_part)))
    if settings.gemini_api_key:
        tasks.append(("gemini", _gemini_opinion(content, media_type, modality, body_part)))
    if settings.radiology_fourth_api_key and settings.radiology_fourth_base_url and settings.radiology_fourth_model:
        tasks.append(("fourth_openai_compatible", _fourth_opinion(content, media_type, modality, body_part)))

    results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True) if tasks else []
    opinions: list[ProviderImageOpinion] = []
    if primary is not None:
        opinions.append(_primary_to_opinion(primary))

    for (provider, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            provider_errors[provider] = _clean(result, 500)
        elif result is not None:
            opinions.append(result)

    if not opinions:
        return None, {
            "ensemble_version": ENSEMBLE_VERSION,
            "ensemble_mode": "no_provider_available",
            "providers_succeeded": [],
            "providers_failed": provider_errors,
            "provider_count": 0,
            "physician_review_required": True,
            "not_diagnostic": True,
        }

    medical_opinions = [item for item in opinions if item.document_kind == "MEDICAL_IMAGE"] or opinions
    consensus, solo = _group_conditions(medical_opinions)
    observations = _merge_text_lists(medical_opinions, "observations", 12)
    limitations = _merge_text_lists(medical_opinions, "limitations", 10)
    critical_flags = _merge_text_lists(medical_opinions, "critical_flags", 8)

    base_review = primary or _review_from_opinion(medical_opinions[0])
    modality_vote = _majority(
        [item.detected_modality for item in medical_opinions], base_review.detected_modality
    )
    body_vote = _majority(
        [item.detected_body_part for item in medical_opinions], base_review.detected_body_part
    )
    summary = _consensus_summary(base_review.summary, consensus, len(medical_opinions))
    synthesized = replace(
        base_review,
        summary=summary,
        observations=observations or base_review.observations,
        limitations=limitations or base_review.limitations,
        model="ensemble:" + ",".join(f"{item.provider}:{item.model}" for item in medical_opinions),
        detected_modality=modality_vote,
        detected_body_part=body_vote,
    )

    provider_payload = [
        {
            "provider": item.provider,
            "model": item.model,
            "document_kind": item.document_kind,
            "detected_modality": item.detected_modality,
            "detected_body_part": item.detected_body_part,
            "summary": item.summary,
            "observations": list(item.observations),
            "candidate_conditions": [
                {"label": c.label, "support": c.support, "confidence": c.confidence}
                for c in item.candidate_conditions
            ],
            "critical_flags": list(item.critical_flags),
            "limitations": list(item.limitations),
        }
        for item in medical_opinions
    ]
    metadata = {
        "ensemble_version": ENSEMBLE_VERSION,
        "ensemble_mode": "independent_multi_provider_consensus",
        "providers_succeeded": [item.provider for item in medical_opinions],
        "providers_failed": provider_errors,
        "provider_count": len(medical_opinions),
        "provider_opinions": provider_payload,
        "consensus_differential": consensus,
        "single_model_differential": solo,
        "critical_review_flags": critical_flags,
        "model_disagreement_present": bool(solo) and len(medical_opinions) >= 2,
        "consensus_is_not_validation": True,
        "physician_review_required": True,
        "not_diagnostic": True,
    }
    return synthesized, metadata
