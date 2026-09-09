"""Multimodal extraction for scanned/image-only medical report PDFs.

This service is extraction-only. It converts a scanned medical report PDF into
source-faithful de-identified text so the existing universal medical-report
clinical summary layer can process it exactly like a text PDF or pasted report.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings


@dataclass(frozen=True)
class ScannedMedicalReportExtraction:
    deidentified_text: str
    document_type: str
    warnings: tuple[str, ...]
    confidence: float
    model: str


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["deidentified_text", "document_type", "warnings", "confidence"],
    "properties": {
        "deidentified_text": {"type": "string"},
        "document_type": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

_INSTRUCTIONS = """
You are MediCore's scanned medical-report extraction component.

Read every visible page of the attached PDF. The PDF may be image-only/scanned and
may contain any kind of medical report: radiology, ultrasound, CT, MRI, pathology,
cytology, endoscopy, cardiology, ECG, echo, Holter, EEG, EMG, pulmonary function,
sleep study, genetics, microbiology, operation/procedure note, discharge summary,
consultation, clinic/emergency note, obstetrics/gynecology, ophthalmology, dental,
dermatology, or another medical report.

This pass is EXTRACTION ONLY:
- Transcribe clinically relevant report text faithfully. Preserve headings when visible.
- Preserve negation, uncertainty and qualifiers exactly in meaning: e.g. "not seen",
  "cannot be excluded", "suspicious", "compatible with", "may represent".
- Preserve measurements, units, dates of examinations/results, grades/stages and
  comparison statements when they are part of the clinical report.
- Do not diagnose, reinterpret, rank probabilities, prescribe, recommend new tests,
  or invent missing content.
- Remove direct identifiers from output: patient name, national ID, protocol/file
  number, phone, address, email and exact date of birth. Age/sex may remain if they
  are clinically printed in the report.
- Do not include signatures, barcodes, QR codes, administrative billing text or
  irrelevant page furniture unless clinically meaningful.
- If some text is unreadable, do not guess; mention that in warnings.
- deidentified_text must be complete enough that another clinician-oriented model
  can summarize the report without seeing the original PDF.
- document_type should be a short source-grounded label such as "Ultrasonografi",
  "Patoloji", "Epikriz", "EKG", or "Diğer tıbbi rapor".

Return only the strict JSON object.
""".strip()


class ScannedMedicalReportExtractionError(RuntimeError):
    pass


async def extract_scanned_medical_report_pdf(
    *,
    content: bytes,
    file_name: str,
) -> ScannedMedicalReportExtraction | None:
    if not content:
        raise ValueError("Boş PDF değerlendirilemez.")

    settings = get_settings()
    if not settings.openai_api_key:
        return None
    model = (settings.openai_lab_model or "").strip()
    if not model:
        return None

    encoded = base64.b64encode(content).decode("ascii")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.responses.create(
            model=model,
            store=False,
            max_output_tokens=14000,
            instructions=_INSTRUCTIONS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "medicore_scanned_medical_report_extraction_v1",
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
                                f"Extract this scanned medical report faithfully. "
                                f"Source filename: {(file_name or 'report.pdf')[:512]}"
                            ),
                        },
                        {
                            "type": "input_file",
                            "filename": (file_name or "report.pdf")[:512],
                            "file_data": f"data:application/pdf;base64,{encoded}",
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        raise ScannedMedicalReportExtractionError(
            f"Taranmış PDF tıbbi metin çıkarımı başarısız: {exc}"
        ) from exc

    output_text = str(getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise ScannedMedicalReportExtractionError(
            "Taranmış PDF modeli boş yanıt döndürdü."
        )
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise ScannedMedicalReportExtractionError(
            "Taranmış PDF modeli geçerli JSON döndürmedi."
        ) from exc

    text = "\n".join(str(payload.get("deidentified_text") or "").splitlines()).strip()
    if len(text) < 10:
        raise ScannedMedicalReportExtractionError(
            "Taranmış PDF'den yeterli klinik metin çıkarılamadı."
        )

    warnings = tuple(
        " ".join(str(item).split()).strip()[:1000]
        for item in (payload.get("warnings") or [])
        if str(item).strip()
    )[:20]
    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    return ScannedMedicalReportExtraction(
        deidentified_text=text[:250_000],
        document_type=" ".join(str(payload.get("document_type") or "").split()).strip()[:160]
        or "Tıbbi rapor",
        warnings=warnings,
        confidence=confidence,
        model=model,
    )
