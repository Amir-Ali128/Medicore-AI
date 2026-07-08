"""ExtractionJob persistence model.

Holds one Claude extraction run whose values are stored for human review before
any deterministic analysis. String statuses only (no enums). No business logic
in the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.analysis_run import AnalysisRun
    from app.infrastructure.database.models.extracted_lab_value import ExtractedLabValue
    from app.infrastructure.database.models.lab_report import LabReport
    from app.infrastructure.database.models.patient import Patient
    from app.infrastructure.database.models.user import User


class ExtractionJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "extraction_jobs"

    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    source_file_name: Mapped[str | None] = mapped_column(String(512))
    source_content_type: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[str] = mapped_column(
        String(32),
        default="pending_review",
        server_default="pending_review",
        nullable=False,
        index=True,
    )
    overall_needs_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    warnings_json: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )

    lab_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lab_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    patient: Mapped["Patient | None"] = relationship()
    uploaded_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[uploaded_by_user_id]
    )
    lab_report: Mapped["LabReport | None"] = relationship()
    analysis_run: Mapped["AnalysisRun | None"] = relationship()
    reviewed_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[reviewed_by_user_id]
    )
    extracted_values: Mapped[list["ExtractedLabValue"]] = relationship(
        back_populates="extraction_job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ExtractionJob id={self.id!s} status={self.status}>"
