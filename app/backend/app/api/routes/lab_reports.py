"""Lab report read routes (summaries only; raw_payload is not exposed)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import LabReportRepositoryDep, SessionDep

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


@router.get("/lab-reports/{lab_report_id}", response_model=LabReportSummary)
async def get_lab_report(
    lab_report_id: uuid.UUID,
    repository: LabReportRepositoryDep,
) -> LabReportSummary:
    report = await repository.get_by_id(lab_report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lab report not found."
        )
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lab report not found."
        )

    metadata = dict(report.metadata_json or {})
    updates: dict[str, Any] = {
        "patient_display_name": payload.display_name,
        "patient_age": payload.age,
        "patient_sex": payload.sex,
        "patient_birth_date": payload.birth_date.isoformat()
        if payload.birth_date is not None
        else None,
        "patient_metadata_source": "pdf_upload",
    }

    for key, value in updates.items():
        if value is not None:
            metadata[key] = value

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
