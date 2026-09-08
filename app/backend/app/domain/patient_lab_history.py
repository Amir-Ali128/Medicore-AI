"""Persistent patient laboratory history for the seven-source native pipeline.

This module connects the source-preserving canonical/native trust contracts to the
existing PostgreSQL LabReport/LabResult tables. It also resolves the most recent
trusted comparable result and delegates numeric movement to TrendEngine, which is
native-C++ first with a behavior-compatible Python fallback.

Native trust is immutable here: review rows stay review rows, suspicious values are
never corrected, and only trusted rows are eligible for longitudinal AI evidence.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ResultStatus, TrendStatus, UserRole
from app.domain.native_lab_engine import native_lab_deterministic_available
from app.domain.trend_engine import TrendEngine
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.patient_timeline_event import PatientTimelineEvent
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.lab_result_repository import LabResultRepository
from app.schemas.trend import TrendComparisonInput

PATIENT_LAB_HISTORY_CONTRACT = "medicore-patient-lab-history-v1"
LONGITUDINAL_TREND_CONTRACT = "medicore-longitudinal-trend-v1"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return value


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _identity_code(row: Mapping[str, Any]) -> str:
    """Stable non-PII identity used to join repeated measurements over time."""
    loinc = str(row.get("loinc_code") or "").strip()
    if loinc:
        return f"LOINC:{loinc.upper()}"[:64]

    name = str(
        row.get("canonical_name")
        or row.get("display_name")
        or row.get("raw_parameter_name")
        or "unknown"
    ).strip().casefold()
    normalized = re.sub(r"[^a-z0-9]+", "_", name).strip("_") or "unknown"
    return f"NAME:{normalized}"[:64]


def _result_status(row: Mapping[str, Any]) -> ResultStatus:
    value = str(row.get("result_status") or "").strip().lower()
    if value == "normal":
        return ResultStatus.NORMAL
    if value == "low":
        return ResultStatus.LOW
    if value == "high":
        return ResultStatus.HIGH
    if value == "needs_review":
        return ResultStatus.NEEDS_REVIEW
    return ResultStatus.UNKNOWN


def _trend_status(value: Any) -> TrendStatus:
    text = str(value or "").strip().lower()
    try:
        return TrendStatus(text)
    except ValueError:
        return TrendStatus.NO_PREVIOUS_RESULT


async def ensure_patient_access(
    session: AsyncSession,
    *,
    patient_id: uuid.UUID,
    current_user: User,
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    if current_user.role == UserRole.PATIENT:
        owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
        if owner_user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    return patient


async def build_longitudinal_trends(
    session: AsyncSession,
    *,
    patient: Patient,
    trust_envelope: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Compare each current trusted row with the latest prior trusted measurement."""
    repository = LabResultRepository(session)
    engine = TrendEngine()
    backend = "native_cpp" if native_lab_deterministic_available() else "python_fallback"
    default_date = _as_date(trust_envelope.get("report_date"))

    trends: list[dict[str, Any]] = []
    trusted_rows = trust_envelope.get("trusted_rows") or []
    for source in trusted_rows:
        if not isinstance(source, Mapping):
            continue
        current_value = _as_decimal(source.get("normalized_value"))
        measured_at = _as_date(source.get("measured_at")) or default_date
        identity_code = _identity_code(source)
        canonical_name = str(source.get("canonical_name") or "").strip() or None
        raw_name = str(source.get("raw_parameter_name") or "").strip() or None

        previous = await repository.latest_previous_match(
            patient.id,
            parameter_code=identity_code,
            canonical_name=canonical_name,
            raw_parameter_name=raw_name,
            before_date=measured_at,
            trusted_only=True,
        )
        trend = engine.compare(
            TrendComparisonInput(
                parameter_id=None,
                parameter_code=identity_code,
                current_value=current_value,
                previous_value=previous.normalized_value if previous else None,
                current_date=measured_at,
                previous_date=previous.measured_at if previous else None,
            )
        )
        trends.append(
            {
                "contract_version": LONGITUDINAL_TREND_CONTRACT,
                "backend": backend,
                "test": source.get("display_name")
                or source.get("canonical_name")
                or source.get("raw_parameter_name"),
                "parameter_code": identity_code,
                "previous_result_id": str(previous.id) if previous else None,
                "previous_value": _json_safe(trend.previous_value),
                "current_value": _json_safe(trend.current_value),
                "previous_measured_at": previous.measured_at.isoformat()
                if previous and previous.measured_at
                else None,
                "current_measured_at": measured_at.isoformat() if measured_at else None,
                "trend_status": trend.trend_status.value,
                "absolute_difference": _json_safe(trend.absolute_difference),
                "percentage_difference": trend.percentage_difference,
                "time_difference_days": trend.time_difference_days,
                "confidence": trend.confidence,
                "reason": trend.reason,
                "needs_review": trend.needs_review,
            }
        )
    return trends


def _trend_by_code(trends: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in trends:
        code = str(item.get("parameter_code") or "")
        if code:
            result[code] = item
    return result


async def persist_patient_lab_case(
    session: AsyncSession,
    *,
    patient: Patient,
    current_user: User,
    canonical_case: Mapping[str, Any],
    trust_envelope: Mapping[str, Any],
    longitudinal_trends: Sequence[Mapping[str, Any]],
    clinical_pipeline: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Atomically persist report, native rows, trends, provenance and AI snapshot."""
    source = trust_envelope.get("source") if isinstance(trust_envelope.get("source"), Mapping) else {}
    report_date = _as_date(trust_envelope.get("report_date"))
    file_name = str(source.get("file_name") or source.get("source_file_name") or "").strip() or None
    trend_index = _trend_by_code(longitudinal_trends)

    report = LabReport(
        patient_id=patient.id,
        uploaded_by_user_id=current_user.id,
        source_type=str(trust_envelope.get("source_type") or "universal_lab")[:64],
        file_name=file_name[:512] if file_name else None,
        report_date=report_date,
        raw_payload=_json_safe(dict(canonical_case)),
        status="analyzed",
        metadata_json={
            "history_contract": PATIENT_LAB_HISTORY_CONTRACT,
            "trust_contract": trust_envelope.get("contract_version"),
            "provenance_contract": trust_envelope.get("provenance_contract_version"),
            "trusted_count": trust_envelope.get("trusted_count"),
            "review_count": trust_envelope.get("review_count"),
            "source": _json_safe(source),
            "longitudinal_trends": _json_safe(longitudinal_trends),
            "clinical_pipeline": _json_safe(clinical_pipeline) if clinical_pipeline else None,
        },
    )
    session.add(report)
    await session.flush()

    persisted: list[LabResult] = []
    all_rows = trust_envelope.get("all_rows") or []
    for source_row in all_rows:
        if not isinstance(source_row, Mapping):
            continue
        identity_code = _identity_code(source_row)
        trend = trend_index.get(identity_code) if bool(source_row.get("trusted_for_ai")) else None
        measured_at = _as_date(source_row.get("measured_at")) or report_date

        result = LabResult(
            patient_id=patient.id,
            lab_report_id=report.id,
            analysis_run_id=None,
            parameter_id=None,
            raw_parameter_name=str(source_row.get("raw_parameter_name") or source_row.get("display_name") or "Unknown")[:255],
            parameter_code=identity_code,
            canonical_name=(str(source_row.get("canonical_name") or source_row.get("display_name") or "")[:255] or None),
            raw_value=(str(source_row.get("raw_value"))[:128] if source_row.get("raw_value") is not None else None),
            normalized_value=_as_decimal(source_row.get("normalized_value")),
            unit=(str(source_row.get("unit") or "")[:64] or None),
            reference_min=_as_decimal(source_row.get("reference_min")),
            reference_max=_as_decimal(source_row.get("reference_max")),
            reference_source=(str(source_row.get("reference_text") or "source_report")[:128]),
            result_status=_result_status(source_row),
            trend_status=_trend_status(trend.get("trend_status") if trend else None),
            previous_value=_as_decimal(trend.get("previous_value")) if trend else None,
            absolute_difference=_as_decimal(trend.get("absolute_difference")) if trend else None,
            percentage_difference=float(trend["percentage_difference"])
            if trend and trend.get("percentage_difference") is not None
            else None,
            time_difference_days=int(trend["time_difference_days"])
            if trend and trend.get("time_difference_days") is not None
            else None,
            alias_confidence=1.0 if source_row.get("canonical_name") else 0.0,
            reference_confidence=1.0
            if source_row.get("reference_min") is not None
            or source_row.get("reference_max") is not None
            or source_row.get("reference_text")
            else 0.0,
            classification_confidence=float(source_row.get("classification_confidence") or 0.0),
            trend_confidence=float(trend.get("confidence") or 0.0) if trend else 0.0,
            needs_review=not bool(source_row.get("trusted_for_ai")),
            reason=str(source_row.get("reason") or "") or None,
            rule_applied=str(source_row.get("rule_applied") or "")[:64] or None,
            measured_at=measured_at,
            metadata_json={
                "history_contract": PATIENT_LAB_HISTORY_CONTRACT,
                "canonical_row_contract": source_row.get("canonical_row_contract"),
                "validation_contract": source_row.get("validation_contract_version"),
                "provenance_contract": source_row.get("provenance_contract_version"),
                "validation_status": source_row.get("validation_status"),
                "trust_status": source_row.get("trust_status"),
                "trust_reason": source_row.get("trust_reason"),
                "trusted_for_ai": bool(source_row.get("trusted_for_ai")),
                "loinc_code": source_row.get("loinc_code"),
                "raw_unit": source_row.get("raw_unit"),
                "reference_text": source_row.get("reference_text"),
                "reference_type": source_row.get("reference_type"),
                "source_type": source_row.get("source_type"),
                "source_file_name": source_row.get("source_file_name"),
                "source_page": source_row.get("source_page"),
                "source_sha256": source_row.get("source_sha256"),
                "source_record_id": source_row.get("source_record_id"),
                "integration_type": source_row.get("integration_type"),
                "ingestion_reasons": _json_safe(source_row.get("ingestion_reasons") or []),
            },
        )
        session.add(result)
        persisted.append(result)

    timeline = PatientTimelineEvent(
        patient_id=patient.id,
        event_type="lab_ingestion",
        status="review_required" if int(trust_envelope.get("review_count") or 0) else "completed",
        title="Laboratuvar sonucu işlendi",
        description="7-source ingestion -> C++ trust -> longitudinal trend -> clinical AI pipeline.",
        occurred_at=datetime.now(timezone.utc),
        source="system",
        source_entity_type="lab_report",
        source_entity_id=report.id,
        actor_user_id=current_user.id,
        lab_report_id=report.id,
        metadata_json={
            "history_contract": PATIENT_LAB_HISTORY_CONTRACT,
            "trusted_count": int(trust_envelope.get("trusted_count") or 0),
            "review_count": int(trust_envelope.get("review_count") or 0),
            "trend_count": len(longitudinal_trends),
            "ai_used": bool(clinical_pipeline and clinical_pipeline.get("ai_used")),
        },
    )
    session.add(timeline)

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return {
        "contract_version": PATIENT_LAB_HISTORY_CONTRACT,
        "patient_id": str(patient.id),
        "lab_report_id": str(report.id),
        "persisted_result_count": len(persisted),
        "trusted_count": int(trust_envelope.get("trusted_count") or 0),
        "review_count": int(trust_envelope.get("review_count") or 0),
        "trend_count": len(longitudinal_trends),
        "doctor_review_required": bool(int(trust_envelope.get("review_count") or 0)),
    }
