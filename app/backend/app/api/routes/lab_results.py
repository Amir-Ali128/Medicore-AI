"""Lab result read routes (structured results; no diagnosis or advice)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import LabResultRepositoryDep
from app.domain.enums import ResultStatus, TrendStatus

router = APIRouter(tags=["lab-results"])


class LabResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_parameter_name: str
    parameter_id: uuid.UUID | None
    parameter_code: str | None
    canonical_name: str | None
    raw_value: str | None
    normalized_value: Decimal | None
    unit: str | None
    reference_min: Decimal | None
    reference_max: Decimal | None
    reference_source: str | None
    result_status: ResultStatus
    trend_status: TrendStatus
    previous_value: Decimal | None
    absolute_difference: Decimal | None
    percentage_difference: float | None
    time_difference_days: int | None
    alias_confidence: float
    reference_confidence: float
    classification_confidence: float
    trend_confidence: float
    needs_review: bool
    reason: str | None
    rule_applied: str | None
    measured_at: date | None
    created_at: datetime


@router.get(
    "/lab-reports/{lab_report_id}/results",
    response_model=list[LabResultResponse],
)
async def list_results_for_report(
    lab_report_id: uuid.UUID,
    repository: LabResultRepositoryDep,
) -> list[LabResultResponse]:
    return list(await repository.list_for_report(lab_report_id))


@router.get(
    "/analysis-runs/{analysis_run_id}/results",
    response_model=list[LabResultResponse],
)
async def list_results_for_analysis_run(
    analysis_run_id: uuid.UUID,
    repository: LabResultRepositoryDep,
) -> list[LabResultResponse]:
    return list(await repository.list_for_analysis_run(analysis_run_id))
