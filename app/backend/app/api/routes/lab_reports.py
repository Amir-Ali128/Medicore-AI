"""Lab report read routes (summaries only; raw_payload is not exposed)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import LabReportRepositoryDep

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
    created_at: datetime
    updated_at: datetime


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


@router.get(
    "/patients/{patient_id}/lab-reports",
    response_model=list[LabReportSummary],
)
async def list_patient_lab_reports(
    patient_id: uuid.UUID,
    repository: LabReportRepositoryDep,
) -> list[LabReportSummary]:
    return list(await repository.list_for_patient(patient_id))
