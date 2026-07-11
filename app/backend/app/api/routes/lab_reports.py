"""Lab report read and clinical-context update routes.

Raw lab payloads are not exposed. Structured patient and clinical context may be
stored in metadata_json so PDF and manually entered reports share the same
physician-review context.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import LabReportRepositoryDep, SessionDep
from app.schemas.lab_analysis import (
    ClinicalAttachmentInput,
    ClinicalHistoryInput,
    ImagingResultsInput,
    PatientInformationInput,
    PhysicalExamInput,
    PresentingComplaintInput,
)

router = APIRouter(tags=["lab-reports"])


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
    """Persist display-only patient metadata extracted from an uploaded PDF."""
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Lab report not found.")

    metadata = dict(report.metadata_json or {})
    updates: dict[str, Any] = {
        "patient_display_name": payload.display_name,
        "patient_age": payload.age,
        "patient_sex": payload.sex,
        "patient_birth_date": (
            payload.birth_date.isoformat() if payload.birth_date is not None else None
        ),
        "patient_metadata_source": "pdf_upload",
    }

    for key, value in updates.items():
        if value is not None:
            metadata[key] = value

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


@router.get(
    "/patients/{patient_id}/lab-reports",
    response_model=list[LabReportSummary],
)
async def list_patient_lab_reports(
    patient_id: uuid.UUID,
    repository: LabReportRepositoryDep,
) -> list[LabReportSummary]:
    return list(await repository.list_for_patient(patient_id))
