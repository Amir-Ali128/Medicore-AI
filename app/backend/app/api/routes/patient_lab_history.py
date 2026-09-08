"""Read-only patient laboratory history and review queue endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.api.routes.lab_results import LabResultResponse
from app.domain.enums import TrendStatus
from app.domain.patient_lab_history import ensure_patient_access
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.lab_result_repository import LabResultRepository

router = APIRouter(prefix="/patients", tags=["patient-lab-history"])
CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


@router.get(
    "/{patient_id}/lab-history",
    response_model=list[LabResultResponse],
)
async def list_patient_lab_history(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    limit: int = 250,
) -> list[LabResultResponse]:
    await ensure_patient_access(
        session,
        patient_id=patient_id,
        current_user=current_user,
    )
    repository = LabResultRepository(session)
    return list(await repository.list_for_patient(patient_id, limit=limit))


@router.get(
    "/{patient_id}/lab-review-queue",
    response_model=list[LabResultResponse],
)
async def list_patient_lab_review_queue(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    limit: int = 250,
) -> list[LabResultResponse]:
    await ensure_patient_access(
        session,
        patient_id=patient_id,
        current_user=current_user,
    )
    repository = LabResultRepository(session)
    return list(await repository.list_review_queue_for_patient(patient_id, limit=limit))


@router.get("/{patient_id}/lab-trends")
async def list_patient_lab_trends(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    limit: int = 250,
) -> dict[str, Any]:
    """Return persisted deterministic trend snapshots, newest first."""
    await ensure_patient_access(
        session,
        patient_id=patient_id,
        current_user=current_user,
    )
    repository = LabResultRepository(session)
    rows = await repository.list_for_patient(patient_id, limit=limit)
    trends = [
        {
            "result_id": str(row.id),
            "parameter_code": row.parameter_code,
            "test": row.canonical_name or row.raw_parameter_name,
            "measured_at": row.measured_at.isoformat() if row.measured_at else None,
            "current_value": float(row.normalized_value) if row.normalized_value is not None else None,
            "previous_value": float(row.previous_value) if row.previous_value is not None else None,
            "trend_status": row.trend_status.value,
            "absolute_difference": float(row.absolute_difference) if row.absolute_difference is not None else None,
            "percentage_difference": row.percentage_difference,
            "time_difference_days": row.time_difference_days,
            "confidence": row.trend_confidence,
        }
        for row in rows
        if row.trend_status != TrendStatus.NO_PREVIOUS_RESULT
    ]
    return {
        "patient_id": str(patient_id),
        "count": len(trends),
        "trends": trends,
    }
