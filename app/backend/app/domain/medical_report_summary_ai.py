"""Universal text medical-report reader and physician-style summarizer.

This service accepts already-extracted report text from any medical specialty,
classifies the report type, and produces a source-faithful clinical summary. It
never invents a diagnosis or recommendation that is not supported by the source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings


REPORT_CATEGORIES = (
    "RADIOLOGY",
    "PATHOLOGY_CYTOLOGY",
    "ENDOSCOPY",
    "CARDIOLOGY_ECHO",
    "ECG",
    "HOLTER",
    "EEG",
    "EMG",
    "PULMONARY_FUNCTION",
    "SLEEP_STUDY",
    "NUCLEAR_MEDICINE",
    "DEXA",
    "OBSTETRIC_GYNECOLOGY",
    "OPERATIVE_NOTE",
    "DISCHARGE_SUMMARY",
    "CONSULTATION",
    "OUTPATIENT_NOTE",
    "EMERGENCY_NOTE",
    "PROCEDURE",
    "GENETIC",
    "MICROBIOLOGY",
    "TRANSFUSION",
    "DENTAL",
    "OPHTHALMOLOGY",
    "DERMATOLOGY",
    "OTHER",
)

_MODALITIES = (
    "XRAY",
    "ULTRASOUND",
    "CT",
    "MRI",
    "MAMMOGRAPHY",
    "DEXA",
    "PET_CT",
    "NUCLEAR_MEDICINE",
    "ENDOSCOPY",
    "PATHOLOGY",
    "ECG",
    "ECHO",
    "EEG",
    "EMG",
    "PFT",
    "OTHER",
    "UNKNOWN",
)

_BODY_PARTS = (
    "BRAIN",
    "HEAD",
    "NECK",
    "CHEST",
    "CARDIAC",
    "ABDOMEN",
    "PELVIS",
    "SPINE",
    "BREAST",
    "THYROID",
    "URINARY",
    "OBSTETRIC",
    "UPPER_EXTREMITY",
    "LOWER_EXTREMITY",
    "MUSCULOSKELETAL",
    "WHOLE_BODY",
    "OTHER",
)


@dataclass(frozen=True)
class MedicalReportReview:
    report_category: str
    report_type: str
    specialty: str
    modality: str
    body_part: str
    doctor_summary: str
    conclusion: str
    key_findings: tuple[str, ...]
    abnormal_findings: tuple[str, ...]
    reassuring_findings: tuple[str, ...]
    recommendations: tuple[str, ...]
    critical_flags: tuple[str, ...]
    comparison_text: str
    limitations: tuple[str, ...]
    confidence: float
    model: str


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "report_category",
        "report_type",
        "specialty",
        "modality",
        "body_part",
        "doctor_summary",
        "conclusion",
        "key_findings",
        "abnormal_findings",
        "reassuring_findings",
        "recommendations",
        "critical_flags",
        "comparison_text",
        "limitations",
        "confidence",
    ],
    "properties": {
        "report_category": {"type": "string", "enum": list(REPORT_CATEGORIES)},
        "report_type": {"type": "string"},
        "specialty": {"type": "string"},
        "modality": {"type": "string", "enum": list(_MODALITIES)},
        "body_part": {"type": "string", "enum": list(_BODY_PARTS)},
        "doctor_summary": {"type": "string"},
        "conclusion": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
        "abnormal_findings": {"type": "array", "items": {"type": "string"}},
        "reassuring_findings": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "critical_flags": {"type": "array", "items": {"type": "string"}},
        "comparison_text": {"type": "string"},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

_INSTRUCTIONS = """
You are MediCore's universal medical-report reading layer. The input is the text
of a medical report, note or procedure document from any specialty. Read it the
way a careful physician would read a report and return a concise Turkish clinical
summary that lets another physician quickly understand what the source says.

Supported content is intentionally open-ended. Examples include radiology (X-ray,
USG/Doppler, CT, MRI, mammography, PET/CT, nuclear medicine, DEXA), pathology and
cytology, endoscopy/colonoscopy, echocardiography, ECG/Holter, EEG/EMG, pulmonary
function, sleep studies, genetics, microbiology, operative/procedure notes,
discharge summaries, consultations, emergency/outpatient notes, obstetric/
gynecologic reports, ophthalmology, dental and other clinical reports. If none
fits exactly, use OTHER and still summarize the report.

Safety and fidelity rules:
- The source report is ground truth. Do not invent findings, diagnoses, stages,
  measurements, treatments, recommendations or negative findings.
- A diagnosis explicitly written in the source may be restated as a source-reported
  diagnosis. Do not upgrade a suspicion/possibility into a definite diagnosis.
- Preserve negation and uncertainty: "izlenmedi", "şüpheli", "uyumlu olabilir",
  "dışlanamaz" and similar wording must keep the same certainty.
- doctor_summary should be 2-6 Turkish sentences, clinically dense and readable,
  similar to a physician's handoff summary. Lead with the most important finding,
  then relevant context/measurements and the report's own conclusion/recommendation.
- conclusion is only the report's explicit SONUÇ/İZLENİM/KANAAT/DIAGNOSIS/CONCLUSION
  meaning. If there is no explicit conclusion section, leave it empty rather than
  inventing one.
- key_findings are important source-derived findings, including meaningful normal
  findings when they affect interpretation.
- abnormal_findings contain only clearly abnormal/positive findings stated by the source.
- reassuring_findings contain only clearly reassuring/negative findings stated by the source.
- recommendations contain only explicit follow-up, referral, repeat test, treatment
  or procedure recommendations written in the source.
- critical_flags contain only explicit urgent/critical source findings. Never infer
  urgency just because a condition could be serious.
- comparison_text contains only explicit comparison with prior studies/results.
- Remove direct identifiers from every output field: patient name, national ID,
  protocol/file number, phone, address, e-mail and exact date of birth.
- Do not prescribe, order tests, provide probability percentages or claim the output
  is a physician diagnosis. This is an assistive summary requiring clinician review.
- Return strict JSON only.
""".strip()


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _string_list(value: object, *, limit: int, item_limit: int = 1200) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = _clean(item, item_limit)
        if cleaned and cleaned not in output:
            output.append(cleaned)
        if len(output) >= limit:
            break
    return tuple(output)


async def summarize_medical_report_text(report_text: str) -> MedicalReportReview | None:
    """Return a universal physician-style summary, or None when AI is not configured."""

    text = report_text.strip()
    if len(text) < 10:
        raise ValueError("Klinik rapor özeti için yeterli metin yok.")

    settings = get_settings()
    if not settings.openai_api_key:
        return None
    model = (settings.openai_lab_model or settings.openai_vision_model or "").strip()
    if not model:
        return None

    # Keep enough source context for multi-page reports while bounding request size.
    bounded_text = text[:120_000]
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(
        model=model,
        store=False,
        max_output_tokens=7000,
        instructions=_INSTRUCTIONS,
        text={
            "format": {
                "type": "json_schema",
                "name": "medicore_medical_report_review_v1",
                "strict": True,
                "schema": _SCHEMA,
            }
        },
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Aşağıdaki tıbbi raporu kaynak metne sadık kalarak değerlendir:\n\n" + bounded_text,
                    }
                ],
            }
        ],
    )

    output_text = str(getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise ValueError("Tıbbi rapor modeli boş yanıt döndürdü.")
    payload = json.loads(output_text)
    if not isinstance(payload, dict):
        raise ValueError("Tıbbi rapor modeli beklenen JSON nesnesini döndürmedi.")

    category = _clean(payload.get("report_category"), 64).upper()
    if category not in REPORT_CATEGORIES:
        category = "OTHER"
    modality = _clean(payload.get("modality"), 64).upper()
    if modality not in _MODALITIES:
        modality = "UNKNOWN"
    body_part = _clean(payload.get("body_part"), 64).upper()
    if body_part not in _BODY_PARTS:
        body_part = "OTHER"

    summary = _clean(payload.get("doctor_summary"), 3600)
    conclusion = _clean(payload.get("conclusion"), 3000)
    key_findings = _string_list(payload.get("key_findings"), limit=30)
    if not summary:
        summary = conclusion or " ".join(key_findings[:4])
    if not summary:
        raise ValueError("Tıbbi rapordan klinik özet üretilemedi.")

    try:
        confidence = float(payload.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return MedicalReportReview(
        report_category=category,
        report_type=_clean(payload.get("report_type"), 180) or "Tıbbi rapor",
        specialty=_clean(payload.get("specialty"), 120) or "Belirtilmemiş",
        modality=modality,
        body_part=body_part,
        doctor_summary=summary,
        conclusion=conclusion,
        key_findings=key_findings,
        abnormal_findings=_string_list(payload.get("abnormal_findings"), limit=24),
        reassuring_findings=_string_list(payload.get("reassuring_findings"), limit=24),
        recommendations=_string_list(payload.get("recommendations"), limit=16),
        critical_flags=_string_list(payload.get("critical_flags"), limit=12),
        comparison_text=_clean(payload.get("comparison_text"), 2200),
        limitations=_string_list(payload.get("limitations"), limit=12),
        confidence=confidence,
        model=model,
    )
