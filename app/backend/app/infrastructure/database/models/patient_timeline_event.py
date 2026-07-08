"""PatientTimelineEvent persistence model.

An operational/product audit trail of patient-related events (uploads, analyses,
extractions, reviews, notes). It is NOT diagnosis, NOT treatment advice, and NOT
patient-facing clinical interpretation. String event types/statuses only (no
enums). No business logic in the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.analysis_run import AnalysisRun
    from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
    from app.infrastructure.database.models.doctor_review import DoctorReview
    from app.infrastructure.database.models.extraction_job import ExtractionJob
    from app.infrastructure.database.models.lab_report import LabReport
    from app.infrastructure.database.models.patient import Patient
    from app.infrastructure.database.models.user import User


class PatientTimelineEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patient_timeline_events"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="info", server_default="info", nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(
        String(32), default="system", server_default="system", nullable=False
    )
    source_entity_type: Mapped[str | None] = mapped_column(String(64))
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lab_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lab_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    clinical_hypothesis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clinical_hypotheses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    doctor_review_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("doctor_reviews.id", ondelete="SET NULL"), nullable=True, index=True
    )
    extraction_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extraction_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    patient: Mapped["Patient"] = relationship()
    actor_user: Mapped["User | None"] = relationship()
    lab_report: Mapped["LabReport | None"] = relationship()
    analysis_run: Mapped["AnalysisRun | None"] = relationship()
    clinical_hypothesis: Mapped["ClinicalHypothesis | None"] = relationship()
    doctor_review: Mapped["DoctorReview | None"] = relationship()
    extraction_job: Mapped["ExtractionJob | None"] = relationship()

    __table_args__ = (
        Index(
            "ix_patient_timeline_events_source_entity",
            "source_entity_type",
            "source_entity_id",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<PatientTimelineEvent id={self.id!s} type={self.event_type} "
            f"status={self.status}>"
        )
