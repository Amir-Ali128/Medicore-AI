"""Direct OpenAI/Astra laboratory document extraction.

Raw PDF/image bytes are sent directly to the configured multimodal OpenAI model.
The model performs document reading, table extraction and semantic normalization in
one request. Deterministic reference-range classification is deliberately left to
the native C++ lab core before any result is persisted.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings

SUPPORTED_LAB_MEDIA_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp"}
)

_LAB_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "patient_age",
        "patient_sex",
        "report_date",
        "labs",
        "critical_findings",
        "clinical_summary",
        "follow_up_considerations",
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
                    "source_page": {"type": ["integer", "null"], "minimum": 1},
                },
            },
        },
        "critical_findings": {"type": "array", "items": {"type": "string"}},
        "clinical_summary": {"type": "string"},
        "follow_up_considerations": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "extraction_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

_INSTRUCTIONS = """
You are the laboratory document reader inside MediCore-AI. Read the ORIGINAL
uploaded laboratory report directly. Perform visual/text preprocessing, table
understanding, extraction and normalization in one pass.

Safety and provenance rules:
- This is physician-assistive software, not an autonomous diagnostic system.
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
- source_page is 1-based when the document has pages; otherwise use null.
- Canonicalize obvious test names (for example HbA1c, Hemoglobin, Creatinine) but
  keep the exact visible test label in raw_parameter_name.
- clinical_summary may describe patterns that deserve physician attention, but
  must not claim a definitive diagnosis or prescribe treatment.
- critical_findings must contain only findings clearly supported by the supplied
  values/reference ranges. Do not invent emergency thresholds.
- follow_up_considerations must be conservative physician-review considerations,
  not treatment instructions.
- Return every clearly visible laboratory result, including normal values.
""".strip()


class OpenAILabExtractionError(RuntimeError):
    pass


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


async def extract_lab_document_with_openai(
    *,
    content: bytes,
    media_type: str,
    file_name: str,
) -> dict[str, Any]:
    """Send the original report directly to Astra/OpenAI and return strict JSON."""
    settings = get_settings()
    normalized_type = (media_type or "").split(";", 1)[0].lower().strip()

    if normalized_type not in SUPPORTED_LAB_MEDIA_TYPES:
        raise ValueError(f"Desteklenmeyen laboratuvar dosya türü: {normalized_type or 'unknown'}")
    if not content:
        raise ValueError("Laboratuvar dosyası boş olamaz.")
    if len(content) > settings.lab_extraction_max_bytes:
        raise ValueError("Laboratuvar dosyası izin verilen boyut sınırını aşıyor.")
    if not settings.openai_api_key:
        raise OpenAILabExtractionError("OPENAI_API_KEY yapılandırılmamış.")

    model = (settings.openai_lab_model or "").strip()
    if not model:
        raise OpenAILabExtractionError("OPENAI_LAB_MODEL yapılandırılmamış.")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.responses.create(
            model=model,
            store=False,
            max_output_tokens=12000,
            instructions=_INSTRUCTIONS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "medicore_lab_document_v1",
                    "strict": True,
                    "schema": _LAB_SCHEMA,
                }
            },
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Process this complete laboratory document directly. "
                                "Extract all visible lab rows, normalize them, preserve "
                                "printed reference ranges, and return the required JSON."
                            ),
                        },
                        _media_block(
                            content=content,
                            media_type=normalized_type,
                            file_name=file_name,
                        ),
                    ],
                }
            ],
        )
    except Exception as exc:  # provider errors are translated at the API boundary
        raise OpenAILabExtractionError(f"OpenAI laboratuvar analizi başarısız: {exc}") from exc

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
