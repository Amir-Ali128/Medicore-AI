"""Lab report read, save-to-patient, file persistence, and clinical-context routes."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text as sql_text

from app.api.dependencies import LabReportRepositoryDep, SessionDep
from app.api.routes.auth import get_current_active_user
from app.domain.enums import UserRole
from app.domain.pdf_privacy import anonymize_lab_pdf
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.schemas.lab_analysis import (
    ClinicalAttachmentInput,
    ClinicalHistoryInput,
    ImagingResultsInput,
    PatientInformationInput,
    PhysicalExamInput,
    PresentingComplaintInput,
)

router = APIRouter(tags=["lab-reports"])

_MAX_LAB_FILE_BYTES = 10 * 1024 * 1024


class LabReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None
    source_type: str
    file_name: str | None
    report_date: date | None
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class LabReportPatientMetadataUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_name: str | None = None
    age: int | None = None
    sex: str | None = None
    birth_date: date | None = None


class LabReportClinicalContextUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_information: PatientInformationInput = Field(
        default_factory=PatientInformationInput
    )
    presenting_complaint: PresentingComplaintInput = Field(
        default_factory=PresentingComplaintInput
    )
    clinical_history_details: ClinicalHistoryInput = Field(
        default_factory=ClinicalHistoryInput
    )
    physical_exam: PhysicalExamInput = Field(default_factory=PhysicalExamInput)
    imaging_results: ImagingResultsInput = Field(default_factory=ImagingResultsInput)
    attachments: list[ClinicalAttachmentInput] = Field(default_factory=list)


class LabReportSaveRequest(BaseModel):
    patient_id: uuid.UUID


def _ensure_patient_access(patient: Patient, current_user: User) -> None:
    if current_user.role != UserRole.PATIENT:
        return

    owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
    if owner_user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")


async def _get_accessible_patient(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: User,
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    _ensure_patient_access(patient, current_user)
    return patient


async def _ensure_lab_file_columns(session: SessionDep) -> None:
    """Add archived-file columns to existing databases without a destructive migration."""
    await session.execute(
        sql_text(
            "ALTER TABLE lab_reports "
            "ADD COLUMN IF NOT EXISTS original_file_data BYTEA"
        )
    )
    await session.execute(
        sql_text(
            "ALTER TABLE lab_reports "
            "ADD COLUMN IF NOT EXISTS original_file_content_type VARCHAR(255)"
        )
    )
    await session.commit()


@router.get("/lab-reports/{lab_report_id}", response_model=LabReportSummary)
async def get_lab_report(
    lab_report_id: uuid.UUID,
    repository: LabReportRepositoryDep,
) -> LabReportSummary:
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Lab report not found.")
    return report


@router.patch(
    "/lab-reports/{lab_report_id}/patient-metadata",
    response_model=LabReportSummary,
)
async def update_lab_report_patient_metadata(
    lab_report_id: uuid.UUID,
    payload: LabReportPatientMetadataUpdate,
    repository: LabReportRepositoryDep,
    session: SessionDep,
) -> LabReportSummary:
    """Persist only coarse demographics; never copy direct PDF identifiers."""
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Lab report not found.")

    metadata = dict(report.metadata_json or {})

    # Remove legacy direct identifiers if an older version wrote them.
    metadata.pop("patient_display_name", None)
    metadata.pop("patient_birth_date", None)

    if payload.age is not None:
        metadata["patient_age"] = payload.age
    if payload.sex:
        metadata["patient_sex"] = payload.sex
    metadata["patient_metadata_source"] = "pdf_upload_privacy_filtered"

    report.metadata_json = metadata
    await session.commit()
    await session.refresh(report)
    return report


@router.patch(
    "/lab-reports/{lab_report_id}/clinical-context",
    response_model=LabReportSummary,
)
async def update_lab_report_clinical_context(
    lab_report_id: uuid.UUID,
    payload: LabReportClinicalContextUpdate,
    repository: LabReportRepositoryDep,
    session: SessionDep,
) -> LabReportSummary:
    """Attach structured intake, examination, imaging, and file metadata."""
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Lab report not found.")

    context = payload.model_dump(mode="json")
    metadata = dict(report.metadata_json or {})
    metadata["clinical_context"] = context
    metadata["clinical_context_source"] = "analysis_workspace"

    patient = context.get("patient_information") or {}
    if patient.get("full_name"):
        metadata["patient_display_name"] = patient["full_name"]
    if patient.get("age") is not None:
        metadata["patient_age"] = patient["age"]
    if patient.get("sex"):
        metadata["patient_sex"] = patient["sex"]
    if patient.get("height_cm") is not None:
        metadata["patient_height_cm"] = patient["height_cm"]
    if patient.get("weight_kg") is not None:
        metadata["patient_weight_kg"] = patient["weight_kg"]

    complaint = context.get("presenting_complaint") or {}
    history = context.get("clinical_history_details") or {}
    metadata["chief_complaint"] = complaint.get("chief_complaint")
    metadata["clinical_history"] = history.get("history_of_present_illness")

    report.metadata_json = metadata
    await session.commit()
    await session.refresh(report)
    return report


@router.patch(
    "/lab-reports/{lab_report_id}/save",
    response_model=LabReportSummary,
)
async def save_lab_report_to_patient(
    lab_report_id: uuid.UUID,
    payload: LabReportSaveRequest,
    repository: LabReportRepositoryDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> LabReportSummary:
    """Attach an analyzed report and its derived rows to the selected patient record."""
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Laboratuvar raporu bulunamadı.")

    await _get_accessible_patient(payload.patient_id, session, current_user)

    report.patient_id = payload.patient_id
    report.uploaded_by_user_id = current_user.id
    metadata = dict(report.metadata_json or {})
    metadata.update(
        {
            "archived": True,
            "archived_at": datetime.now(UTC).isoformat(),
            "saved_by_user_id": str(current_user.id),
        }
    )
    report.metadata_json = metadata

    params = {
        "patient_id": str(payload.patient_id),
        "lab_report_id": str(lab_report_id),
    }
    await session.execute(
        sql_text(
            "UPDATE analysis_runs SET patient_id = :patient_id "
            "WHERE lab_report_id = :lab_report_id"
        ),
        params,
    )
    await session.execute(
        sql_text(
            "UPDATE lab_results SET patient_id = :patient_id "
            "WHERE lab_report_id = :lab_report_id"
        ),
        params,
    )
    await session.execute(
        sql_text(
            "UPDATE clinical_hypotheses SET patient_id = :patient_id "
            "WHERE lab_report_id = :lab_report_id"
        ),
        params,
    )

    await session.commit()
    await session.refresh(report)
    return report


@router.post(
    "/lab-reports/{lab_report_id}/file",
    response_model=LabReportSummary,
)
async def store_lab_report_original_file(
    lab_report_id: uuid.UUID,
    repository: LabReportRepositoryDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
) -> LabReportSummary:
    """Anonymize a PDF and persist only the privacy-filtered bytes."""
    await _ensure_lab_file_columns(session)
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Laboratuvar raporu bulunamadı.")

    await _get_accessible_patient(report.patient_id, session, current_user)

    filename = (file.filename or report.file_name or "laboratuvar-raporu.pdf").strip()
    content_type = (file.content_type or "").lower().strip()
    if not filename.lower().endswith(".pdf") and content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Yalnızca PDF dosyası saklanabilir.")

    content = await file.read(_MAX_LAB_FILE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Boş PDF dosyası kaydedilemez.")
    if len(content) > _MAX_LAB_FILE_BYTES:
        raise HTTPException(status_code=413, detail="PDF dosyası 10 MB sınırını aşıyor.")

    try:
        anonymized = anonymize_lab_pdf(content)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "PDF anonimleştirilemedi; kişisel bilgi içerebilecek özgün dosya "
                f"arşive kaydedilmedi. {exc}"
            ),
        ) from exc

    stored_content_type = "application/pdf"
    await session.execute(
        sql_text(
            "UPDATE lab_reports "
            "SET original_file_data = :content, "
            "original_file_content_type = :content_type, "
            "updated_at = NOW() "
            "WHERE id = :lab_report_id"
        ),
        {
            "content": anonymized.content,
            "content_type": stored_content_type,
            "lab_report_id": str(lab_report_id),
        },
    )

    metadata = dict(report.metadata_json or {})
    metadata.update(
        {
            "original_file_stored": True,
            "original_file_anonymized": True,
            "original_file_size_bytes": len(anonymized.content),
            "original_file_content_type": stored_content_type,
            "original_file_saved_at": datetime.now(UTC).isoformat(),
            "original_file_redaction_count": anonymized.redaction_count,
        }
    )
    report.metadata_json = metadata
    if not report.file_name:
        report.file_name = filename

    await session.commit()
    await session.refresh(report)
    return report


@router.get("/lab-reports/{lab_report_id}/file")
async def open_lab_report_original_file(
    lab_report_id: uuid.UUID,
    repository: LabReportRepositoryDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    """Return the stored anonymized PDF inline for the authorized patient/user."""
    await _ensure_lab_file_columns(session)
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Laboratuvar raporu bulunamadı.")

    await _get_accessible_patient(report.patient_id, session, current_user)

    row = (
        await session.execute(
            sql_text(
                "SELECT original_file_data, original_file_content_type "
                "FROM lab_reports WHERE id = :lab_report_id"
            ),
            {"lab_report_id": str(lab_report_id)},
        )
    ).mappings().one_or_none()

    if not row or row["original_file_data"] is None:
        raise HTTPException(
            status_code=404,
            detail="Bu kaydın PDF'i saklanmamış. PDF'i yeniden yükleyip Kaydet'e basın.",
        )

    filename = report.file_name or "laboratuvar-raporu.pdf"
    encoded_filename = quote(filename, safe="")
    return Response(
        content=bytes(row["original_file_data"]),
        media_type=row["original_file_content_type"] or "application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/lab-reports/{lab_report_id}", status_code=204)
async def delete_lab_report(
    lab_report_id: uuid.UUID,
    repository: LabReportRepositoryDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    """Delete an accessible archived lab report, its PDF bytes, and derived rows."""
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Laboratuvar raporu bulunamadı.")

    await _get_accessible_patient(report.patient_id, session, current_user)

    # Hypotheses use SET NULL for report deletion, so remove report-specific ones
    # explicitly instead of leaving detached clinical suggestions behind.
    await session.execute(
        sql_text("DELETE FROM clinical_hypotheses WHERE lab_report_id = :lab_report_id"),
        {"lab_report_id": str(lab_report_id)},
    )
    await session.delete(report)
    await session.commit()
    return Response(status_code=204)


@router.get(
    "/patients/{patient_id}/lab-reports",
    response_model=list[LabReportSummary],
)
async def list_patient_lab_reports(
    patient_id: uuid.UUID,
    repository: LabReportRepositoryDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[LabReportSummary]:
    await _get_accessible_patient(patient_id, session, current_user)
    return list(await repository.list_for_patient(patient_id))
