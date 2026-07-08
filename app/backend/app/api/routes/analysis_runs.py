"""Analysis run read routes (summaries with counts and timestamps)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import AnalysisRunRepositoryDep

router = APIRouter(tags=["analysis-runs"])


class AnalysisRunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    lab_report_id: uuid.UUID
    status: str
    total_results: int
    normal_count: int
    low_count: int
    high_count: int
    needs_review_count: int
    unknown_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@router.get("/analysis-runs/{analysis_run_id}", response_model=AnalysisRunSummary)
async def get_analysis_run(
    analysis_run_id: uuid.UUID,
    repository: AnalysisRunRepositoryDep,
) -> AnalysisRunSummary:
    run = await repository.get_by_id(analysis_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found."
        )
    return run


@router.get(
    "/lab-reports/{lab_report_id}/analysis-runs",
    response_model=list[AnalysisRunSummary],
)
async def list_analysis_runs_for_report(
    lab_report_id: uuid.UUID,
    repository: AnalysisRunRepositoryDep,
) -> list[AnalysisRunSummary]:
    return list(await repository.list_for_report(lab_report_id))
