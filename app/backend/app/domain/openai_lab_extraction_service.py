"""Direct OpenAI/Astra laboratory document extraction.

Raw PDF/image bytes are sent directly to the configured multimodal OpenAI model.
This first pass is intentionally extraction-only: document reading, table parsing and
semantic normalization happen here; deterministic classification/calculation happens
in native C++, and clinical synthesis happens only after native validation.
"""

from __future__ import annotations

import base64
from functools import lru_cache
import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings

SUPPORTED_LAB_MEDIA_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp"}
)
_MAX_DOCUMENTS_PER_REQUEST = 12
_EXTRACTION_TIMEOUT_SECONDS = 18.0

_LAB_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "patient_age",
        "patient_sex",
        "report_date",
        "labs",
        "warnings",
        "extraction_confidence",
    ],
    "properties": {
        "patient_age": {"type": ["integer", "null"], "minimum": 0, "maximum": 130},
        "patient_sex": {"type": ["string", "null"]},
        "report_date": {"type": ["string", "null"]},
        "labs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "raw_parameter_name",
                    "canonical_name",
                    "raw_value",
                    "normalized_value",
                    "unit",
                    "reference_min",
                    "reference_max",
                    "reference_text",
                    "measured_at",
                    "needs_review",
                    "confidence",
                    "source_file_name",
                    "source_page",
                ],
                "properties": {
                    "raw_parameter_name": {"type": "string"},
                    "canonical_name": {"type": ["string", "null"]},
                    "raw_value": {"type": ["string", "null"]},
                    "normalized_value": {"type": ["number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "reference_min": {"type": ["number", "null"]},
                    "reference_max": {"type": ["number", "null"]},
                    "reference_text": {"type": ["string", "null"]},
                    "measured_at": {"type": ["string", "null"]},
                    "needs_review": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_file_name": {"type": ["string", "null"]},
                    "source_page": {"type": ["integer", "null"], "minimum": 1},
                },
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
        "extraction_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

_INSTRUCTIONS = """
You are the extraction-only laboratory document reader inside MediCore-AI. Read ALL
ORIGINAL uploaded laboratory report files as one case. Perform visual/text
preprocessing, table understanding, extraction and normalization in one pass.

Safety and provenance rules:
- Do not diagnose, interpret clinical significance, rank clinical risk or recommend
  treatment in this pass. A later layer does clinical synthesis after native C++
  validation.
- Never output a patient's name, national identity number, protocol number,
  address, phone, email or exact date of birth. Coarse age and sex may be returned
  only when explicitly visible and useful for physician review.
- Never invent a test, value, unit, date or reference range.
- Preserve the laboratory's printed reference interval. One-sided limits are
  allowed: use null for the missing side and keep the original rule in
  reference_text.
- normalized_value must represent the observed numeric result, never a reference
  limit or a historical value.
- If digits, decimal separators, units, row association or reference limits are
  visually ambiguous, set needs_review=true and lower confidence.
- source_file_name must identify the supplied source label for the row.
- source_page is 1-based within that source file when it has pages; otherwise null.
- Canonicalize obvious test names (for example HbA1c, Hemoglobin, Creatinine) but
  keep the exact visible test label in raw_parameter_name.
- Merge the supplied files into one logical report/case. Do not duplicate a lab row
  merely because adjacent uploaded images overlap.
- Return every clearly visible laboratory result, including normal values.
- warnings should contain extraction/provenance uncertainties only, not clinical
  interpretation.
""".strip()


class OpenAILabExtractionError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _client_for_key(api_key: str) -> AsyncOpenAI:
    """Reuse the connection pool and never let provider retries multiply latency."""
    return AsyncOpenAI(
        api_key=api_key,
        timeout=_EXTRACTION_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _media_block(*, content: bytes, media_type: str, file_name: str) -> dict[str, Any]:
    encoded = base64.b64encode(content).decode("ascii")
    if media_type == "application/pdf":
        return {
            "type": "input_file",
            "filename": file_name or "lab-report.pdf",
            "file_data": f"data:application/pdf;base64,{encoded}",
        }
    return {
        "type": "input_image",
        "image_url": f"data:{media_type};base64,{encoded}",
        "detail": "high",
    }


def _normalized_media_type(media_type: str) -> str:
    return (media_type or "").split(";", 1)[0].lower().strip()


async def extract_lab_documents_with_openai(
    *,
    documents: list[tuple[bytes, str, str]],
) -> dict[str, Any]:
    """Send one or more original report files to Astra/OpenAI in a single request."""
    settings = get_settings()
    if not documents:
        raise ValueError("En az bir laboratuvar dosyası gerekir.")
    if len(documents) > _MAX_DOCUMENTS_PER_REQUEST:
        raise ValueError(f"Tek analizde en fazla {_MAX_DOCUMENTS_PER_REQUEST} dosya gönderilebilir.")

    total_bytes = 0
    content_parts: list[dict[str, Any]] = [
        {
            "type": "input_text",
            "text": (
                "Process every attached source as one laboratory case. Extract all "
                "visible rows, normalize them, preserve printed references and return "
                "the required extraction JSON. Source labels are authoritative for provenance."
            ),
        }
    ]

    for index, (content, media_type, file_name) in enumerate(documents, start=1):
        normalized_type = _normalized_media_type(media_type)
        if normalized_type not in SUPPORTED_LAB_MEDIA_TYPES:
            raise ValueError(
                f"Desteklenmeyen laboratuvar dosya türü: {normalized_type or 'unknown'}"
            )
        if not content:
            raise ValueError(f"Laboratuvar dosyası boş: {file_name or index}")

        total_bytes += len(content)
        safe_name = (file_name or f"lab-source-{index}")[:512]
        content_parts.append(
            {
                "type": "input_text",
                "text": f"SOURCE {index} filename: {safe_name}",
            }
        )
        content_parts.append(
            _media_block(
                content=content,
                media_type=normalized_type,
                file_name=safe_name,
            )
        )

    if total_bytes > settings.lab_extraction_max_bytes:
        raise ValueError("Laboratuvar dosyalarının toplamı izin verilen boyut sınırını aşıyor.")
    if not settings.openai_api_key:
        raise OpenAILabExtractionError("OPENAI_API_KEY yapılandırılmamış.")

    model = (settings.openai_lab_model or "").strip()
    if not model:
        raise OpenAILabExtractionError("OPENAI_LAB_MODEL yapılandırılmamış.")

    client = _client_for_key(settings.openai_api_key)
    try:
        response = await client.responses.create(
            model=model,
            store=False,
            max_output_tokens=12000,
            instructions=_INSTRUCTIONS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "medicore_lab_document_v2",
                    "strict": True,
                    "schema": _LAB_SCHEMA,
                }
            },
            input=[{"role": "user", "content": content_parts}],
        )
    except Exception as exc:  # provider errors are translated at the API boundary
        raise OpenAILabExtractionError(
            f"OpenAI laboratuvar analizi {_EXTRACTION_TIMEOUT_SECONDS:.0f} sn bütçesinde tamamlanamadı: {exc}"
        ) from exc

    output_text = str(getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise OpenAILabExtractionError("OpenAI laboratuvar modeli boş yanıt döndürdü.")

    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise OpenAILabExtractionError("OpenAI laboratuvar çıktısı geçerli JSON değil.") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("labs"), list):
        raise OpenAILabExtractionError("OpenAI laboratuvar çıktısı beklenen şemada değil.")
    return payload


async def extract_lab_document_with_openai(
    *,
    content: bytes,
    media_type: str,
    file_name: str,
) -> dict[str, Any]:
    """Backward-compatible single-document wrapper."""
    return await extract_lab_documents_with_openai(
        documents=[(content, media_type, file_name)]
    )
