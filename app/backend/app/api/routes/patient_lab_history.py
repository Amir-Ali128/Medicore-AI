"""Read-only patient laboratory history and review queue endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.api.routes.lab_results import LabResultResponse
from app.domain.enums import TrendStatus
from app.domain.patient_lab_history import PATIENT_LAB_HISTORY_CONTRACT, ensure_patient_access
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.lab_report_repository import LabReportRepository
from app.infrastructure.database.repositories.lab_result_repository import LabResultRepository

router = APIRouter(prefix="/patients", tags=["patient-lab-history"])
CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


def _json_number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _string_number(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _row_status(row: LabResult) -> str:
    value = getattr(row.result_status, "value", row.result_status)
    return str(value or "unknown").lower()


def _latest_row_payload(row: LabResult) -> dict[str, Any]:
    metadata = row.metadata_json if isinstance(row.metadata_json, Mapping) else {}
    status = _row_status(row)
    trusted = not bool(row.needs_review) and status in {"normal", "low", "high"}
    return {
        "display_name": row.canonical_name or row.raw_parameter_name,
        "raw_parameter_name": row.raw_parameter_name,
        "canonical_name": row.canonical_name,
        "parameter_code": row.parameter_code,
        "raw_value": row.raw_value,
        "normalized_value": _json_number(row.normalized_value),
        "unit": row.unit,
        "reference_min": _json_number(row.reference_min),
        "reference_max": _json_number(row.reference_max),
        "reference_text": metadata.get("reference_text"),
        "result_status": status.upper(),
        "needs_review": bool(row.needs_review),
        "trusted_for_ai": trusted,
        "reason": row.reason,
        "classification_confidence": row.classification_confidence,
        "measured_at": row.measured_at.isoformat() if row.measured_at else None,
    }


def _legacy_analysis_payload(row: LabResult) -> dict[str, Any]:
    status = _row_status(row)
    return {
        "lab_result_id": str(row.id),
        "raw_parameter_name": row.raw_parameter_name,
        "parameter_id": str(row.parameter_id) if row.parameter_id else None,
        "parameter_code": row.parameter_code,
        "canonical_name": row.canonical_name,
        "normalized_value": _string_number(row.normalized_value) or "",
        "unit": row.unit or "",
        "reference_min": _string_number(row.reference_min),
        "reference_max": _string_number(row.reference_max),
        "result_status": status,
        "trend_status": getattr(row.trend_status, "value", str(row.trend_status or "")),
        "needs_review": bool(row.needs_review),
        "reason": row.reason or "",
        "alias_confidence": float(row.alias_confidence or 0.0),
        "reference_confidence": float(row.reference_confidence or 0.0),
        "classification_confidence": float(row.classification_confidence or 0.0),
        "trend_confidence": float(row.trend_confidence or 0.0),
    }


def _latest_lab_snapshot(
    report: LabReport,
    rows: Sequence[LabResult],
) -> dict[str, Any]:
    metadata = report.metadata_json if isinstance(report.metadata_json, Mapping) else {}
    source = metadata.get("source") if isinstance(metadata.get("source"), Mapping) else {}
    trends = metadata.get("longitudinal_trends")
    longitudinal_trends = list(trends) if isinstance(trends, list) else []
    clinical_pipeline = (
        metadata.get("clinical_pipeline")
        if isinstance(metadata.get("clinical_pipeline"), Mapping)
        else {}
    )
    clinical_assessment = (
        clinical_pipeline.get("clinical_assessment")
        if isinstance(clinical_pipeline, Mapping)
        else None
    )

    all_rows = [_latest_row_payload(row) for row in rows]
    trusted_rows = [row for row in all_rows if row["trusted_for_ai"]]
    review_rows = [row for row in all_rows if not row["trusted_for_ai"]]
    trusted_count = int(metadata.get("trusted_count") or len(trusted_rows))
    review_count = int(metadata.get("review_count") or len(review_rows))
    patient_history = {
        "contract_version": PATIENT_LAB_HISTORY_CONTRACT,
        "patient_id": str(report.patient_id),
        "lab_report_id": str(report.id),
        "persisted_result_count": len(rows),
        "trusted_count": trusted_count,
        "review_count": review_count,
        "trend_count": len(longitudinal_trends),
        "doctor_review_required": review_count > 0,
    }

    return {
        "contract_version": "medicore-latest-patient-lab-v1",
        "source_type": report.source_type,
        "source": dict(source),
        "file_name": report.file_name,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "patient_id": str(report.patient_id),
        "lab_report_id": str(report.id),
        "trusted_count": trusted_count,
        "review_count": review_count,
        "processed_row_count": len(rows),
        "doctor_review_required": review_count > 0,
        "longitudinal_trends": longitudinal_trends,
        "clinical_assessment": clinical_assessment,
        "ai_attempted": bool(clinical_pipeline.get("ai_attempted")) if clinical_pipeline else False,
        "ai_used": bool(clinical_pipeline.get("ai_used")) if clinical_pipeline else False,
        "trusted_rows": trusted_rows,
        "review_rows": review_rows,
        "results": [_legacy_analysis_payload(row) for row in rows],
        "patient_history": patient_history,
        "history_contract_version": PATIENT_LAB_HISTORY_CONTRACT,
    }


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


@router.get("/{patient_id}/lab-latest")
async def get_latest_patient_lab_report(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    """Return the latest persisted lab report in both universal and legacy UI shapes."""
    await ensure_patient_access(
        session,
        patient_id=patient_id,
        current_user=current_user,
    )
    report_repository = LabReportRepository(session)
    reports = await report_repository.list_for_patient(patient_id)
    if not reports:
        raise HTTPException(status_code=404, detail="Bu hasta için kayıtlı laboratuvar raporu yok.")

    report = reports[0]
    result_repository = LabResultRepository(session)
    rows = await result_repository.list_for_report(report.id)
    return _latest_lab_snapshot(report, rows)


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
