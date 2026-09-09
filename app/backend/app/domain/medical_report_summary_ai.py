"""Universal text medical-report reader and physician-style summarizer.

This service accepts already-extracted report text from any medical specialty,
classifies the report type, and produces a source-faithful structured clinical
summary. It never invents a diagnosis or recommendation that is not supported
by the source report.
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
    main_result: str
    technical_findings: tuple[str, ...]
    clinical_interpretation: str
    doctor_summary: str
    brief_summary: str
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
        "main_result",
        "technical_findings",
        "clinical_interpretation",
        "doctor_summary",
        "brief_summary",
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
        "main_result": {"type": "string"},
        "technical_findings": {"type": "array", "items": {"type": "string"}},
        "clinical_interpretation": {"type": "string"},
        "doctor_summary": {"type": "string"},
        "brief_summary": {"type": "string"},
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
review that lets another physician understand the source quickly.

Supported content is intentionally open-ended: radiology, pathology/cytology,
endoscopy, echocardiography, ECG/Holter, EEG/EMG, pulmonary function, sleep
studies, genetics, microbiology, operative/procedure notes, discharge summaries,
consultations, emergency/outpatient notes, obstetric/gynecologic reports,
ophthalmology, dental, dermatology and other clinical reports. If no category
fits exactly, use OTHER and still summarize the report.

OUTPUT CONTRACT — keep these meanings distinct:
1. main_result: 1-2 sentences. State the single most important source-supported
   result first. Include the decisive classification/measurement when it changes
   meaning. Example domains: a genetic variant plus its reported classification,
   a pathology diagnosis, the dominant radiology impression, the main ECHO/ECG
   abnormality, or the principal endoscopy finding.
2. technical_findings: compact source-derived identifiers/measurements needed to
   understand the result. Examples: HGVS variant, zygosity, ACMG class, dimensions,
   EF, pressure gradient, stage/grade, organism/susceptibility, histologic markers.
   Do not add generic technical details that do not affect interpretation.
3. clinical_interpretation: 1-3 sentences explaining what the source result means
   clinically, but only to the degree supported by the report itself. Preserve
   reported disease association, inheritance/de-novo information, phenotype match,
   severity, stage or stated significance. Never turn an association into certainty.
4. doctor_summary: 2-6 dense Turkish sentences, like a physician handoff. It may
   combine main result, relevant context, explicit conclusion and explicit advice.
5. brief_summary: one short final sentence, suitable for a "Kısaca" box. It must
   be clinically useful, not conversational, and must not contain arrows unless
   they improve clarity.
6. conclusion: only the source report's explicit SONUÇ/İZLENİM/KANAAT/DIAGNOSIS/
   CONCLUSION meaning. If there is no explicit conclusion, return an empty string.
7. key_findings: important additional source-derived findings not already reduced
   to the main result. Include clinically meaningful negative findings when needed.
8. recommendations: only recommendations explicitly present in the source.

Safety and fidelity rules:
- The source report is ground truth. Do not invent findings, diagnoses, stages,
  measurements, treatments, recommendations, inheritance patterns or negative findings.
- A diagnosis explicitly written in the source may be restated as source-reported.
  Do not upgrade suspicion, association, "uyumlu olabilir", "dışlanamaz" or
  "yüksek olasılıkla" wording into a definite fact.
- Preserve negation and uncertainty exactly in meaning.
- For genetics, preserve exact variant notation, zygosity, reported ACMG class,
  inheritance model, parental testing, de-novo wording and recurrence-risk comments
  only when they are in the source. Do not independently reclassify a variant.
- abnormal_findings contain only clearly abnormal/positive source findings.
- reassuring_findings contain only clearly reassuring/negative source findings.
- critical_flags contain only explicit urgent/critical source findings. Never infer
  urgency merely because a condition can be serious.
- comparison_text contains only explicit comparison with prior studies/results.
- Remove direct identifiers from every output field: patient name, national ID,
  protocol/file number, phone, address, e-mail and exact date of birth.
- Do not prescribe, order tests, provide invented probability percentages or claim
  the output is a physician diagnosis. This is an assistive summary requiring review.
- Do not ask the user questions, offer to explain more, say "istersen", or append a
  chatbot-style conversational tail. End with the medical summary itself.
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
    """Return a universal structured physician-style summary, or None if unconfigured."""

    text = report_text.strip()
    if len(text) < 10:
        raise ValueError("Klinik rapor özeti için yeterli metin yok.")

    settings = get_settings()
    if not settings.openai_api_key:
        return None
    model = (settings.openai_lab_model or settings.openai_vision_model or "").strip()
    if not model:
        return None

    bounded_text = text[:120_000]
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.create(
        model=model,
        store=False,
        max_output_tokens=8000,
        instructions=_INSTRUCTIONS,
        text={
            "format": {
                "type": "json_schema",
                "name": "medicore_medical_report_review_v2",
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
                        "text": (
                            "Aşağıdaki tıbbi raporu kaynak metne sadık kalarak, "
                            "Ana Sonuç → Teknik Bulgular → Klinik Yorum → Önemli Bulgular → "
                            "Öneriler → Kısaca mantığıyla değerlendir:\n\n" + bounded_text
                        ),
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

    main_result = _clean(payload.get("main_result"), 2600)
    clinical_interpretation = _clean(payload.get("clinical_interpretation"), 3200)
    doctor_summary = _clean(payload.get("doctor_summary"), 4200)
    brief_summary = _clean(payload.get("brief_summary"), 1200)
    conclusion = _clean(payload.get("conclusion"), 3000)
    technical_findings = _string_list(payload.get("technical_findings"), limit=20)
    key_findings = _string_list(payload.get("key_findings"), limit=30)

    if not main_result:
        main_result = conclusion or " ".join(key_findings[:2]) or doctor_summary
    if not doctor_summary:
        doctor_summary = main_result or conclusion or " ".join(key_findings[:4])
    if not brief_summary:
        brief_summary = main_result[:900]
    if not doctor_summary:
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
        main_result=main_result,
        technical_findings=technical_findings,
        clinical_interpretation=clinical_interpretation,
        doctor_summary=doctor_summary,
        brief_summary=brief_summary,
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
