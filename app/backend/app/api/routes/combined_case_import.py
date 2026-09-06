"""Universal case import for PDFs and photographed/scanned medical pages.

Whatever clinically relevant content is present is extracted first. No fixed headings
or mandatory clinical/lab/radiology trio is required. Laboratory data then enters the
native C++ lab pipeline; visible radiology report text is persisted as report evidence.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import SessionDep
from app.api.routes import lab_pdf_direct_upload
from app.api.routes.lab_analysis import DEMO_PATIENT_ID, DEMO_UPLOADED_BY_USER_ID
from app.api.routes.radiology_reports import _persist_report
from app.domain.openai_case_document_service import (
    OpenAICaseDocumentError,
    SUPPORTED_CASE_MEDIA_TYPES,
    extract_case_documents_with_openai,
)
from app.schemas.lab_analysis import (
    AnalysisPipelineResult,
    ClinicalHistoryInput,
    ImagingResultsInput,
    PatientInformationInput,
    PhysicalExamInput,
    PresentingComplaintInput,
)
from app.schemas.radiology_report import RadiologyReportCreate, RadiologyReportResponse

router = APIRouter(prefix="/combined-case", tags=["combined-case"])

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
_EXTENSION_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class ClinicalContextResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_information: PatientInformationInput = Field(default_factory=PatientInformationInput)
    presenting_complaint: PresentingComplaintInput = Field(default_factory=PresentingComplaintInput)
    clinical_history_details: ClinicalHistoryInput = Field(default_factory=ClinicalHistoryInput)
    physical_exam: PhysicalExamInput = Field(default_factory=PhysicalExamInput)
    imaging_results: ImagingResultsInput = Field(default_factory=ImagingResultsInput)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class SectionSummary(BaseModel):
    """Backward-compatible counts plus what the universal reader actually detected."""

    model_config = ConfigDict(frozen=True)

    clinical_characters: int = 0
    laboratory_characters: int = 0
    radiology_characters: int = 0
    parsed_lab_values: int = 0
    detected_content_types: list[str] = Field(default_factory=list)


class CombinedCaseImportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    clinical_context: ClinicalContextResponse = Field(default_factory=ClinicalContextResponse)
    lab_analysis: AnalysisPipelineResult | None = None
    radiology_report: RadiologyReportResponse | None = None
    sections: SectionSummary = Field(default_factory=SectionSummary)
    document_summary: str = ""
    medications: list[dict[str, Any]] = Field(default_factory=list)
    other_findings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _media_type(file: UploadFile) -> str:
    declared = (file.content_type or "").split(";", 1)[0].lower().strip()
    if declared in SUPPORTED_CASE_MEDIA_TYPES:
        return declared
    return _EXTENSION_MEDIA_TYPES.get(Path(file.filename or "").suffix.lower(), declared)


def _clean_text(value: Any) -> str | None:
    text = " ".join(str(value or "").split()).strip()
    return text or None


def _join_text(values: list[Any]) -> str | None:
    parts = [_clean_text(value) for value in values]
    return "\n".join(part for part in parts if part) or None


def _medication_text(medications: list[dict[str, Any]]) -> str | None:
    lines: list[str] = []
    for item in medications:
        name = _clean_text(item.get("name"))
        if not name:
            continue
        details = [
            _clean_text(item.get("dose")),
            _clean_text(item.get("frequency")),
            _clean_text(item.get("route")),
            _clean_text(item.get("status")),
        ]
        suffix = " | ".join(value for value in details if value)
        lines.append(f"{name}: {suffix}" if suffix else name)
    return "\n".join(lines) or None


def _clinical_context(payload: dict[str, Any]) -> ClinicalContextResponse:
    clinical = payload.get("clinical") if isinstance(payload.get("clinical"), dict) else {}
    vitals = payload.get("vitals") if isinstance(payload.get("vitals"), dict) else {}
    medications = payload.get("medications") if isinstance(payload.get("medications"), list) else []
    radiology = payload.get("radiology") if isinstance(payload.get("radiology"), list) else []

    imaging: dict[str, str | None] = {
        "xray": None,
        "ultrasound": None,
        "ct": None,
        "mri": None,
        "pet_ct": None,
        "pathology": None,
    }
    imaging_buckets: dict[str, list[str]] = {key: [] for key in imaging}
    modality_map = {
        "XRAY": "xray",
        "X-RAY": "xray",
        "CR": "xray",
        "DX": "xray",
        "US": "ultrasound",
        "ULTRASOUND": "ultrasound",
        "CT": "ct",
        "MRI": "mri",
        "MR": "mri",
        "PET": "pet_ct",
        "PET/CT": "pet_ct",
        "PET-CT": "pet_ct",
        "PATHOLOGY": "pathology",
    }
    for entry in radiology:
        if not isinstance(entry, dict):
            continue
        modality = str(entry.get("modality") or "").strip().upper()
        key = modality_map.get(modality)
        if not key:
            continue
        text = _join_text([
            entry.get("report_text"),
            "\n".join(str(item) for item in (entry.get("findings") or [])),
            entry.get("impression"),
        ])
        if text:
            imaging_buckets[key].append(text)
    for key, values in imaging_buckets.items():
        imaging[key] = _join_text(values)

    return ClinicalContextResponse(
        patient_information=PatientInformationInput(
            age=payload.get("patient_age"),
            sex=_clean_text(payload.get("patient_sex")),
            height_cm=clinical.get("height_cm"),
            weight_kg=clinical.get("weight_kg"),
        ),
        presenting_complaint=PresentingComplaintInput(
            reason_for_visit=_clean_text(clinical.get("reason_for_visit")),
            chief_complaint=_clean_text(clinical.get("chief_complaint")),
            complaint_duration=_clean_text(clinical.get("complaint_duration")),
            associated_symptoms=_clean_text(clinical.get("associated_symptoms")),
        ),
        clinical_history_details=ClinicalHistoryInput(
            history_of_present_illness=_clean_text(clinical.get("history_of_present_illness")),
            current_medical_conditions=_clean_text(clinical.get("current_medical_conditions")),
            past_medical_history=_clean_text(clinical.get("past_medical_history")),
            family_history=_clean_text(clinical.get("family_history")),
            medications=_medication_text([item for item in medications if isinstance(item, dict)]),
            allergies=_clean_text(clinical.get("allergies")),
            tobacco_alcohol=_clean_text(clinical.get("tobacco_alcohol")),
            past_surgeries=_clean_text(clinical.get("past_surgeries")),
        ),
        physical_exam=PhysicalExamInput(
            blood_pressure_systolic=vitals.get("blood_pressure_systolic"),
            blood_pressure_diastolic=vitals.get("blood_pressure_diastolic"),
            pulse_bpm=vitals.get("pulse_bpm"),
            temperature_c=vitals.get("temperature_c"),
            respiratory_rate=vitals.get("respiratory_rate"),
            oxygen_saturation_percent=vitals.get("oxygen_saturation_percent"),
            examination_findings=_clean_text(clinical.get("examination_findings")),
        ),
        imaging_results=ImagingResultsInput(**imaging),
    )


def _radiology_text(entries: list[dict[str, Any]]) -> str | None:
    blocks: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        heading = " / ".join(
            value for value in [
                _clean_text(entry.get("modality")),
                _clean_text(entry.get("body_part")),
            ] if value
        )
        body = _join_text([
            entry.get("report_text"),
            "\n".join(str(item) for item in (entry.get("findings") or [])),
            entry.get("impression"),
        ])
        if body:
            blocks.append(f"{heading}\n{body}" if heading else body)
    return "\n\n".join(blocks) or None


def _clinical_character_count(context: ClinicalContextResponse) -> int:
    payload = context.model_dump(mode="json")
    total = 0
    stack: list[Any] = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str):
            total += len(value)
    return total


@router.post(
    "/upload",
    response_model=CombinedCaseImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_combined_case_document(
    session: SessionDep,
    file: UploadFile = File(...),
) -> CombinedCaseImportResponse:
    """Analyze whatever clinical content exists in one PDF or uploaded page image."""
    filename = (file.filename or "case-document").strip() or "case-document"
    media_type = _media_type(file)
    if media_type not in SUPPORTED_CASE_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vaka analizi için PDF, JPG/JPEG, PNG veya WEBP yükleyin.",
        )

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Yüklenen vaka dosyası boş.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Vaka dosyası 15 MB sınırını aşıyor.")

    documents = [(content, media_type, filename)]
    try:
        payload = await extract_case_documents_with_openai(documents=documents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OpenAICaseDocumentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    content_types = [
        str(item).strip() for item in (payload.get("content_types") or []) if str(item).strip()
    ]
    labs = payload.get("labs") if isinstance(payload.get("labs"), list) else []
    radiology_entries = [
        item for item in (payload.get("radiology") or []) if isinstance(item, dict)
    ]
    medications = [
        item for item in (payload.get("medications") or []) if isinstance(item, dict)
    ]
    other_findings = [
        str(item).strip() for item in (payload.get("other_findings") or []) if str(item).strip()
    ]
    warnings = [
        str(item).strip() for item in (payload.get("warnings") or []) if str(item).strip()
    ]

    context = _clinical_context(payload)

    lab_analysis: AnalysisPipelineResult | None = None
    if labs:
        # The lab route deliberately re-reads the original source so its strict lab
        # extraction contract and native C++ truth layer remain authoritative.
        lab_analysis = await lab_pdf_direct_upload._analyze_prepared_documents(
            session=session,
            documents=documents,
        )

    radiology_report: RadiologyReportResponse | None = None
    report_text = _radiology_text(radiology_entries)
    if report_text:
        radiology_payload = RadiologyReportCreate(
            patient_id=DEMO_PATIENT_ID,
            uploaded_by_user_id=DEMO_UPLOADED_BY_USER_ID,
            report_date=date.today(),
            report_text=report_text,
            file_name=filename,
            metadata_json={
                "source": "universal_case_ai_document",
                "content_type": media_type,
                "upload_size_bytes": len(content),
                "detected_content_types": content_types,
                "extraction_confidence": payload.get("extraction_confidence"),
            },
        )
        radiology_report = await _persist_report(
            payload=radiology_payload,
            source_type="universal_case_ai_document",
            session=session,
        )

    if "medical_image" in content_types and not report_text:
        warnings.append(
            "Gerçek tıbbi görüntü algılandı; bu belge okuyucu görüntü tanısı üretmez. "
            "Görüntü, native vision/radyoloji inceleme hattında ayrıca değerlendirilmelidir."
        )

    if not content_types and not labs and not radiology_entries and not other_findings:
        warnings.append("Yüklenen sayfada güvenilir klinik içerik sınıflandırılamadı.")

    radiology_characters = len(report_text or "")
    lab_characters = sum(
        len(str(item.get("raw_parameter_name") or ""))
        + len(str(item.get("raw_value") or item.get("normalized_value") or ""))
        for item in labs
        if isinstance(item, dict)
    )

    return CombinedCaseImportResponse(
        clinical_context=context,
        lab_analysis=lab_analysis,
        radiology_report=radiology_report,
        sections=SectionSummary(
            clinical_characters=_clinical_character_count(context),
            laboratory_characters=lab_characters,
            radiology_characters=radiology_characters,
            parsed_lab_values=len(labs),
            detected_content_types=content_types,
        ),
        document_summary=_clean_text(payload.get("document_summary")) or "",
        medications=medications,
        other_findings=other_findings,
        warnings=warnings,
    )
