"""Universal PDF/page extraction for MediCore cases.

The model reads whatever clinically relevant content is actually present in the
uploaded PDF/image. It does not require predefined section headings and it does
not diagnose in this pass. Deterministic lab math/classification remains native C++.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings

SUPPORTED_CASE_MEDIA_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/webp"}
)
_MAX_DOCUMENTS_PER_REQUEST = 12

_LAB_ROW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "raw_parameter_name", "canonical_name", "raw_value", "normalized_value",
        "unit", "reference_min", "reference_max", "reference_text", "measured_at",
        "needs_review", "confidence", "source_file_name", "source_page",
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
}

_NULLABLE_TEXT = {"type": ["string", "null"]}
_NULLABLE_NUMBER = {"type": ["number", "null"]}
_NULLABLE_INTEGER = {"type": ["integer", "null"]}

_CASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "content_types", "document_summary", "patient_age", "patient_sex", "report_date",
        "clinical", "vitals", "medications", "labs", "radiology", "other_findings",
        "warnings", "extraction_confidence",
    ],
    "properties": {
        "content_types": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "clinical_history", "symptoms", "physical_exam", "vitals",
                    "laboratory", "radiology_report", "medical_image", "medications",
                    "allergies", "pathology", "procedure", "diagnosis_text", "other",
                ],
            },
        },
        "document_summary": {"type": "string"},
        "patient_age": {"type": ["integer", "null"], "minimum": 0, "maximum": 130},
        "patient_sex": {"type": ["string", "null"]},
        "report_date": {"type": ["string", "null"]},
        "clinical": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "reason_for_visit", "chief_complaint", "complaint_duration",
                "associated_symptoms", "history_of_present_illness",
                "current_medical_conditions", "past_medical_history", "family_history",
                "allergies", "tobacco_alcohol", "past_surgeries", "examination_findings",
                "height_cm", "weight_kg",
            ],
            "properties": {
                "reason_for_visit": _NULLABLE_TEXT,
                "chief_complaint": _NULLABLE_TEXT,
                "complaint_duration": _NULLABLE_TEXT,
                "associated_symptoms": _NULLABLE_TEXT,
                "history_of_present_illness": _NULLABLE_TEXT,
                "current_medical_conditions": _NULLABLE_TEXT,
                "past_medical_history": _NULLABLE_TEXT,
                "family_history": _NULLABLE_TEXT,
                "allergies": _NULLABLE_TEXT,
                "tobacco_alcohol": _NULLABLE_TEXT,
                "past_surgeries": _NULLABLE_TEXT,
                "examination_findings": _NULLABLE_TEXT,
                "height_cm": _NULLABLE_NUMBER,
                "weight_kg": _NULLABLE_NUMBER,
            },
        },
        "vitals": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "blood_pressure_systolic", "blood_pressure_diastolic", "pulse_bpm",
                "temperature_c", "respiratory_rate", "oxygen_saturation_percent",
            ],
            "properties": {
                "blood_pressure_systolic": _NULLABLE_INTEGER,
                "blood_pressure_diastolic": _NULLABLE_INTEGER,
                "pulse_bpm": _NULLABLE_INTEGER,
                "temperature_c": _NULLABLE_NUMBER,
                "respiratory_rate": _NULLABLE_INTEGER,
                "oxygen_saturation_percent": _NULLABLE_NUMBER,
            },
        },
        "medications": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "dose", "frequency", "route", "status", "source_page"],
                "properties": {
                    "name": {"type": "string"},
                    "dose": _NULLABLE_TEXT,
                    "frequency": _NULLABLE_TEXT,
                    "route": _NULLABLE_TEXT,
                    "status": _NULLABLE_TEXT,
                    "source_page": {"type": ["integer", "null"], "minimum": 1},
                },
            },
        },
        "labs": {"type": "array", "items": _LAB_ROW_SCHEMA},
        "radiology": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "modality", "body_part", "report_text", "findings", "impression",
                    "source_file_name", "source_page", "confidence",
                ],
                "properties": {
                    "modality": _NULLABLE_TEXT,
                    "body_part": _NULLABLE_TEXT,
                    "report_text": _NULLABLE_TEXT,
                    "findings": {"type": "array", "items": {"type": "string"}},
                    "impression": _NULLABLE_TEXT,
                    "source_file_name": _NULLABLE_TEXT,
                    "source_page": {"type": ["integer", "null"], "minimum": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "other_findings": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "extraction_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

_INSTRUCTIONS = """
You are MediCore's universal extraction-only case document reader. Read every
attached PDF or page image and extract ALL clinically relevant content that is
actually visible. The upload can contain any mixture of clinical notes, symptoms,
vitals, medication lists, laboratory tables, radiology reports, pathology text,
procedures or other medical information. Do not require headings and do not require
all categories to be present.

Rules:
- This pass is extraction only. Do not diagnose, prescribe, rank disease probability
  or invent missing medical facts.
- Never output direct identifiers: patient name, national ID, protocol number,
  address, phone, email or exact date of birth. Coarse age and sex may be returned.
- If a category is absent, return an empty array or null fields rather than guessing.
- Preserve visible laboratory values, units, dates and printed reference ranges.
- For laboratory rows use the same strict row semantics as the MediCore lab reader.
- For radiology, copy only clinically meaningful report/findings/impression text that
  is visibly present; do not infer an imaging diagnosis from a photo of a report.
- If the uploaded page itself is a true medical image, mark medical_image in
  content_types, but do not invent image findings in this extraction service.
- Preserve source filename/page provenance wherever the schema supports it.
- document_summary should briefly state what kinds of clinical information are
  present, not provide a diagnosis.
- warnings are extraction/provenance uncertainties only.
""".strip()


class OpenAICaseDocumentError(RuntimeError):
    pass


def _media_block(*, content: bytes, media_type: str, file_name: str) -> dict[str, Any]:
    encoded = base64.b64encode(content).decode("ascii")
    if media_type == "application/pdf":
        return {
            "type": "input_file",
            "filename": file_name or "case.pdf",
            "file_data": f"data:application/pdf;base64,{encoded}",
        }
    return {
        "type": "input_image",
        "image_url": f"data:{media_type};base64,{encoded}",
        "detail": "high",
    }


def _normalized_media_type(media_type: str) -> str:
    return (media_type or "").split(";", 1)[0].lower().strip()


async def extract_case_documents_with_openai(
    *, documents: list[tuple[bytes, str, str]],
) -> dict[str, Any]:
    settings = get_settings()
    if not documents:
        raise ValueError("En az bir vaka dosyası gerekir.")
    if len(documents) > _MAX_DOCUMENTS_PER_REQUEST:
        raise ValueError(f"Tek vakada en fazla {_MAX_DOCUMENTS_PER_REQUEST} dosya gönderilebilir.")

    total_bytes = 0
    parts: list[dict[str, Any]] = [{
        "type": "input_text",
        "text": (
            "Analyze whatever clinically relevant content is present in all attached "
            "sources as one case. Do not require fixed sections. Return the strict JSON."
        ),
    }]
    for index, (content, media_type, file_name) in enumerate(documents, start=1):
        normalized = _normalized_media_type(media_type)
        if normalized not in SUPPORTED_CASE_MEDIA_TYPES:
            raise ValueError(f"Desteklenmeyen vaka dosya türü: {normalized or 'unknown'}")
        if not content:
            raise ValueError(f"Vaka dosyası boş: {file_name or index}")
        total_bytes += len(content)
        safe_name = (file_name or f"case-source-{index}")[:512]
        parts.append({"type": "input_text", "text": f"SOURCE {index} filename: {safe_name}"})
        parts.append(_media_block(content=content, media_type=normalized, file_name=safe_name))

    if total_bytes > settings.lab_extraction_max_bytes:
        raise ValueError("Vaka dosyalarının toplamı izin verilen boyut sınırını aşıyor.")
    if not settings.openai_api_key:
        raise OpenAICaseDocumentError("OPENAI_API_KEY yapılandırılmamış.")
    model = (settings.openai_lab_model or "").strip()
    if not model:
        raise OpenAICaseDocumentError("OPENAI_LAB_MODEL yapılandırılmamış.")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.responses.create(
            model=model,
            store=False,
            max_output_tokens=16000,
            instructions=_INSTRUCTIONS,
            text={"format": {
                "type": "json_schema",
                "name": "medicore_universal_case_document_v1",
                "strict": True,
                "schema": _CASE_SCHEMA,
            }},
            input=[{"role": "user", "content": parts}],
        )
    except Exception as exc:
        raise OpenAICaseDocumentError(f"OpenAI vaka belge analizi başarısız: {exc}") from exc

    output_text = str(getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise OpenAICaseDocumentError("OpenAI vaka belge modeli boş yanıt döndürdü.")
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise OpenAICaseDocumentError("OpenAI vaka belge çıktısı geçerli JSON değil.") from exc
    if not isinstance(payload, dict):
        raise OpenAICaseDocumentError("OpenAI vaka belge çıktısı beklenen şemada değil.")
    return payload
