"""AnalysisRun persistence model.

Represents one deterministic analysis pass over a lab report, with aggregate
status counts. No Claude summary or doctor-review fields yet. No business logic
in the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.lab_report import LabReport
    from app.infrastructure.database.models.lab_result import LabResult
    from app.infrastructure.database.models.patient import Patient


class AnalysisRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_runs"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lab_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    total_results: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    normal_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    low_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    high_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    needs_review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    unknown_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    patient: Mapped["Patient"] = relationship()
    lab_report: Mapped["LabReport"] = relationship(back_populates="analysis_runs")
    lab_results: Mapped[list["LabResult"]] = relationship(
        back_populates="analysis_run",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<AnalysisRun id={self.id!s} report={self.lab_report_id!s} "
            f"status={self.status} total={self.total_results}>"
        )
