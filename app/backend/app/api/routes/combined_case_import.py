"""Import one text-based PDF and split it into clinical, laboratory, and radiology sections."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import AnalysisPipelineDep, SessionDep
from app.api.routes.lab_analysis import (
    DEMO_PATIENT_ID,
    DEMO_UPLOADED_BY_USER_ID,
    _ensure_demo_patient_and_user,
    _extract_text_from_pdf,
    _parse_lab_values_from_text,
)
from app.api.routes.radiology_reports import _persist_report
from app.schemas.lab_analysis import (
    AnalysisPipelineResult,
    ClinicalHistoryInput,
    ImagingResultsInput,
    MockLabReportInput,
    PatientInformationInput,
    PatientMetadataOutput,
    PhysicalExamInput,
    PresentingComplaintInput,
)
from app.schemas.radiology_report import RadiologyReportCreate, RadiologyReportResponse

router = APIRouter(prefix="/combined-case", tags=["combined-case"])

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class ClinicalContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_information: PatientInformationInput
    presenting_complaint: PresentingComplaintInput
    clinical_history_details: ClinicalHistoryInput
    physical_exam: PhysicalExamInput
    imaging_results: ImagingResultsInput = Field(default_factory=ImagingResultsInput)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class SectionSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    clinical_characters: int
    laboratory_characters: int
    radiology_characters: int
    parsed_lab_values: int


class CombinedCaseImportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    clinical_context: ClinicalContextResponse
    lab_analysis: AnalysisPipelineResult
    radiology_report: RadiologyReportResponse
    sections: SectionSummary
    warnings: list[str] = Field(default_factory=list)


_SECTION_HEADINGS: dict[str, set[str]] = {
    "clinical": {
        "HASTA BILGILERI VE KLINIK BULGULAR",
        "HASTA BILGILERI KLINIK BULGULAR",
        "KLINIK HASTA BILGILERI",
        "KLINIK BILGILER",
    },
    "laboratory": {
        "KAN TAHLILLERI",
        "KAN TAHLILI SONUCLARI",
        "LABORATUVAR SONUCLARI",
        "LABORATUVAR BULGULARI",
    },
    "radiology": {
        "RADYOLOJI RAPORU",
        "RADYOLOJI BULGULARI",
        "GORUNTULEME RAPORU",
        "GORUNTULEME BULGULARI",
    },
}

_FIELD_ALIASES: dict[str, str] = {
    "HASTA ADI SOYADI": "full_name",
    "AD SOYAD": "full_name",
    "HASTA ADI": "full_name",
    "YAS": "age",
    "CINSIYET": "sex",
    "BOY": "height_cm",
    "BOY CM": "height_cm",
    "KILO": "weight_kg",
    "KILO KG": "weight_kg",
    "BASVURU NEDENI": "reason_for_visit",
    "ANA SIKAYET": "chief_complaint",
    "SIKAYET": "chief_complaint",
    "SIKAYET SURESI": "complaint_duration",
    "SURE": "complaint_duration",
    "SIDDET": "severity_score",
    "AGRI SIDDETI": "severity_score",
    "ESLIK EDEN BELIRTILER": "associated_symptoms",
    "ESLIK EDEN SIKAYETLER": "associated_symptoms",
    "SIKAYETIN OYKUSU": "history_of_present_illness",
    "HASTALIK OYKUSU": "history_of_present_illness",
    "MEVCUT HASTALIKLAR": "current_medical_conditions",
    "GECMIS SAGLIK OYKUSU": "past_medical_history",
    "OZ GECMIS": "past_medical_history",
    "AILE OYKUSU": "family_history",
    "ILACLAR": "medications",
    "KULLANILAN ILACLAR": "medications",
    "ALERJILER": "allergies",
    "SIGARA ALKOL": "tobacco_alcohol",
    "SIGARA VE ALKOL": "tobacco_alcohol",
    "AMELIYATLAR": "past_surgeries",
    "GECIRILMIS AMELIYATLAR": "past_surgeries",
    "TANSIYON": "blood_pressure",
    "NABIZ": "pulse_bpm",
    "ATES": "temperature_c",
    "VUCUT SICAKLIGI": "temperature_c",
    "SOLUNUM": "respiratory_rate",
    "SOLUNUM SAYISI": "respiratory_rate",
    "SPO2": "oxygen_saturation_percent",
    "OKSIJEN SATURASYONU": "oxygen_saturation_percent",
    "MUAYENE BULGULARI": "examination_findings",
    "FIZIK MUAYENE": "examination_findings",
}


def _fold_text(value: str) -> str:
    replacements = {
        "İ": "I",
        "ı": "I",
        "Ş": "S",
        "ş": "S",
        "Ğ": "G",
        "ğ": "G",
        "Ü": "U",
        "ü": "U",
        "Ö": "O",
        "ö": "O",
        "Ç": "C",
        "ç": "C",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = value.upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _section_name(line: str) -> str | None:
    folded = _fold_text(line)
    for section_name, headings in _SECTION_HEADINGS.items():
        if folded in headings:
            return section_name
    return None


def _split_sections(text: str) -> dict[str, str]:
    buffers: dict[str, list[str]] = {name: [] for name in _SECTION_HEADINGS}
    active_section: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if active_section is not None and buffers[active_section]:
                buffers[active_section].append("")
            continue

        section_name = _section_name(line)
        if section_name is not None:
            active_section = section_name
            continue

        if active_section is not None:
            buffers[active_section].append(line)

    sections = {
        name: "\n".join(lines).strip()
        for name, lines in buffers.items()
    }
    missing = [name for name, section_text in sections.items() if not section_text]
    if missing:
        readable = {
            "clinical": "HASTA BİLGİLERİ VE KLİNİK BULGULAR",
            "laboratory": "KAN TAHLİLLERİ",
            "radiology": "RADYOLOJİ RAPORU",
        }
        missing_labels = ", ".join(readable[name] for name in missing)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "PDF üç bölüme ayrılamadı. Eksik veya boş başlıklar: "
                f"{missing_labels}. Başlıkları ayrı satırlarda kullanın."
            ),
        )
    return sections


def _parse_labelled_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    active_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^(.{2,60}?)\s*[:=]\s*(.*)$", line)
        if match:
            alias = _FIELD_ALIASES.get(_fold_text(match.group(1)))
            if alias:
                fields[alias] = match.group(2).strip()
                active_key = alias
                continue

        if active_key and line:
            fields[active_key] = f"{fields[active_key]} {line}".strip()

    return fields


def _number(value: str | None) -> float | None:
    if not value:
        return None
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _integer(value: str | None) -> int | None:
    parsed = _number(value)
    return int(parsed) if parsed is not None else None


def _normalize_sex(value: str | None) -> str | None:
    if not value:
        return None
    folded = _fold_text(value)
    if folded.startswith("KADIN") or folded.startswith("FEMALE"):
        return "female"
    if folded.startswith("ERKEK") or folded.startswith("MALE"):
        return "male"
    return "unknown"


def _parse_clinical_context(text: str) -> ClinicalContextResponse:
    fields = _parse_labelled_fields(text)

    systolic: int | None = None
    diastolic: int | None = None
    blood_pressure = fields.get("blood_pressure")
    if blood_pressure:
        pressure_match = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", blood_pressure)
        if pressure_match:
            systolic = int(pressure_match.group(1))
            diastolic = int(pressure_match.group(2))

    patient_information = PatientInformationInput(
        full_name=fields.get("full_name"),
        age=_integer(fields.get("age")),
        sex=_normalize_sex(fields.get("sex")),
        height_cm=_number(fields.get("height_cm")),
        weight_kg=_number(fields.get("weight_kg")),
    )
    presenting_complaint = PresentingComplaintInput(
        reason_for_visit=fields.get("reason_for_visit"),
        chief_complaint=fields.get("chief_complaint"),
        complaint_duration=fields.get("complaint_duration"),
        severity_score=_integer(fields.get("severity_score")),
        associated_symptoms=fields.get("associated_symptoms"),
    )
    clinical_history = ClinicalHistoryInput(
        history_of_present_illness=fields.get("history_of_present_illness"),
        current_medical_conditions=fields.get("current_medical_conditions"),
        past_medical_history=fields.get("past_medical_history"),
        family_history=fields.get("family_history"),
        medications=fields.get("medications"),
        allergies=fields.get("allergies"),
        tobacco_alcohol=fields.get("tobacco_alcohol"),
        past_surgeries=fields.get("past_surgeries"),
    )
    physical_exam = PhysicalExamInput(
        blood_pressure_systolic=systolic,
        blood_pressure_diastolic=diastolic,
        pulse_bpm=_integer(fields.get("pulse_bpm")),
        temperature_c=_number(fields.get("temperature_c")),
        respiratory_rate=_integer(fields.get("respiratory_rate")),
        oxygen_saturation_percent=_number(fields.get("oxygen_saturation_percent")),
        examination_findings=fields.get("examination_findings"),
    )

    return ClinicalContextResponse(
        patient_information=patient_information,
        presenting_complaint=presenting_complaint,
        clinical_history_details=clinical_history,
        physical_exam=physical_exam,
    )


@router.post(
    "/upload",
    response_model=CombinedCaseImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_combined_case_pdf(
    pipeline: AnalysisPipelineDep,
    session: SessionDep,
    file: UploadFile = File(...),
) -> CombinedCaseImportResponse:
    filename = file.filename or "combined-case.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Birleşik vaka aktarımı yalnızca PDF dosyalarını destekler.",
        )

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Yüklenen PDF boş.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF 15 MB sınırını aşıyor.")

    extracted_text = _extract_text_from_pdf(content)
    if not extracted_text.strip():
        raise HTTPException(
            status_code=400,
            detail="PDF'den seçilebilir metin çıkarılamadı. Taranmış PDF için OCR gerekir.",
        )

    sections = _split_sections(extracted_text)
    clinical_context = _parse_clinical_context(sections["clinical"])
    lab_values = _parse_lab_values_from_text(sections["laboratory"])
    if not lab_values:
        raise HTTPException(
            status_code=400,
            detail=(
                "KAN TAHLİLLERİ bölümünde desteklenen sonuç bulunamadı. "
                "Her sonuç tek satırda 'WBC 17.8 K/mm3 4.50 - 11.00' biçiminde olmalı."
            ),
        )

    if len(sections["radiology"]) < 10:
        raise HTTPException(status_code=400, detail="RADYOLOJİ RAPORU bölümü çok kısa.")

    await _ensure_demo_patient_and_user()

    lab_payload = MockLabReportInput(
        patient_id=DEMO_PATIENT_ID,
        uploaded_by_user_id=DEMO_UPLOADED_BY_USER_ID,
        file_name=filename,
        report_date=date.today(),
        patient_information=clinical_context.patient_information,
        presenting_complaint=clinical_context.presenting_complaint,
        clinical_history_details=clinical_context.clinical_history_details,
        physical_exam=clinical_context.physical_exam,
        imaging_results=clinical_context.imaging_results,
        attachments=[],
        chief_complaint=clinical_context.presenting_complaint.chief_complaint,
        clinical_history=clinical_context.clinical_history_details.history_of_present_illness,
        values=lab_values,
    )
    lab_analysis = await pipeline.run(lab_payload)
    patient = clinical_context.patient_information
    lab_analysis = lab_analysis.model_copy(
        update={
            "patient": PatientMetadataOutput(
                display_name=patient.full_name,
                age=patient.age,
                sex=patient.sex,
                height_cm=patient.height_cm,
                weight_kg=patient.weight_kg,
            )
        }
    )

    radiology_payload = RadiologyReportCreate(
        patient_id=DEMO_PATIENT_ID,
        uploaded_by_user_id=DEMO_UPLOADED_BY_USER_ID,
        report_date=date.today(),
        report_text=sections["radiology"],
        file_name=filename,
        metadata_json={
            "source": "combined_case_pdf",
            "content_type": file.content_type,
            "upload_size_bytes": len(content),
        },
    )
    radiology_record = await _persist_report(
        payload=radiology_payload,
        source_type="combined_case_pdf",
        session=session,
    )

    warnings: list[str] = []
    if not patient.full_name:
        warnings.append("Hasta adı klinik bölümünden çıkarılamadı.")
    if not clinical_context.presenting_complaint.chief_complaint:
        warnings.append("Ana şikayet klinik bölümünden çıkarılamadı.")
    if not clinical_context.physical_exam.examination_findings:
        warnings.append("Muayene bulguları klinik bölümünden çıkarılamadı.")

    return CombinedCaseImportResponse(
        clinical_context=clinical_context,
        lab_analysis=lab_analysis,
        radiology_report=RadiologyReportResponse.model_validate(radiology_record),
        sections=SectionSummary(
            clinical_characters=len(sections["clinical"]),
            laboratory_characters=len(sections["laboratory"]),
            radiology_characters=len(sections["radiology"]),
            parsed_lab_values=len(lab_values),
        ),
        warnings=warnings,
    )
