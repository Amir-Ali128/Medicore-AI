"""LabResult persistence model.

One structured, deterministically-classified lab value. Holds the resolved
parameter mapping, the numeric value, the resolved reference range, the rule
outcome, and the trend snapshot. No business logic in the model.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ResultStatus, TrendStatus
from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    result_status_enum,
    trend_status_enum,
)

if TYPE_CHECKING:
    from app.infrastructure.database.models.analysis_run import AnalysisRun
    from app.infrastructure.database.models.clinical_parameter import ClinicalParameter
    from app.infrastructure.database.models.lab_report import LabReport
    from app.infrastructure.database.models.patient import Patient


class LabResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lab_results"

    # --- Foreign keys ----------------------------------------------------
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lab_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parameter_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinical_parameters.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # --- Parameter mapping ----------------------------------------------
    raw_parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parameter_code: Mapped[str | None] = mapped_column(String(64), index=True)
    canonical_name: Mapped[str | None] = mapped_column(String(255))

    # --- Value & reference ----------------------------------------------
    raw_value: Mapped[str | None] = mapped_column(String(128))
    normalized_value: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(String(64))
    reference_min: Mapped[Decimal | None] = mapped_column(Numeric)
    reference_max: Mapped[Decimal | None] = mapped_column(Numeric)
    reference_source: Mapped[str | None] = mapped_column(String(128))

    # --- Deterministic classification -----------------------------------
    result_status: Mapped[ResultStatus] = mapped_column(
        result_status_enum, default=ResultStatus.UNKNOWN, nullable=False, index=True
    )
    trend_status: Mapped[TrendStatus] = mapped_column(
        trend_status_enum, default=TrendStatus.NO_PREVIOUS_RESULT, nullable=False
    )

    # --- Trend snapshot --------------------------------------------------
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric)
    absolute_difference: Mapped[Decimal | None] = mapped_column(Numeric)
    percentage_difference: Mapped[float | None] = mapped_column(Float)
    time_difference_days: Mapped[int | None] = mapped_column(Integer)

    # --- Confidence & review --------------------------------------------
    alias_confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    reference_confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    trend_confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    needs_review: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False, index=True)

    reason: Mapped[str | None] = mapped_column(Text)
    rule_applied: Mapped[str | None] = mapped_column(String(64))

    measured_at: Mapped[date | None] = mapped_column(Date, index=True)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    patient: Mapped["Patient"] = relationship()
    lab_report: Mapped["LabReport"] = relationship(back_populates="results")
    analysis_run: Mapped["AnalysisRun | None"] = relationship(back_populates="lab_results")
    clinical_parameter: Mapped["ClinicalParameter | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<LabResult id={self.id!s} param={self.parameter_code!r} "
            f"status={self.result_status.value} review={self.needs_review}>"
        )
