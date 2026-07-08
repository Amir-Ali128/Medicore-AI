"""ClinicalHypothesis persistence model.

A system/AI-suggested clinical possibility — NOT a final diagnosis. Every
hypothesis defaults to pending doctor review; clinical validity only follows a
doctor's action. No business logic lives in the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.analysis_run import AnalysisRun
    from app.infrastructure.database.models.doctor_review import DoctorReview
    from app.infrastructure.database.models.lab_report import LabReport
    from app.infrastructure.database.models.patient import Patient
    from app.infrastructure.database.models.user import User


class ClinicalHypothesis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clinical_hypotheses"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lab_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lab_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis_type: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(32))

    status: Mapped[str] = mapped_column(
        String(32),
        default="pending_review",
        server_default="pending_review",
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(32), default="system", server_default="system", nullable=False
    )

    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )

    needs_doctor_review: Mapped[bool] = mapped_column(
        default=True, server_default="true", nullable=False, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    patient: Mapped["Patient"] = relationship()
    lab_report: Mapped["LabReport | None"] = relationship()
    analysis_run: Mapped["AnalysisRun | None"] = relationship()
    reviewed_by_user: Mapped["User | None"] = relationship()
    doctor_reviews: Mapped[list["DoctorReview"]] = relationship(
        back_populates="clinical_hypothesis",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ClinicalHypothesis id={self.id!s} status={self.status} "
            f"needs_review={self.needs_doctor_review}>"
        )
