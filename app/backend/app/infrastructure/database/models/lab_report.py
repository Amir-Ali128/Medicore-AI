"""LabReport persistence model.

Stores an ingested lab report (currently mock JSON payloads) and links it to the
patient, the uploading user, its structured results, and its analysis runs. No
business logic lives here — it is a pure persistence model.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.analysis_run import AnalysisRun
    from app.infrastructure.database.models.lab_result import LabResult
    from app.infrastructure.database.models.patient import Patient
    from app.infrastructure.database.models.user import User


class LabReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lab_reports"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(64), default="mock_json", server_default="mock_json", nullable=False
    )
    file_name: Mapped[str | None] = mapped_column(String(512))
    report_date: Mapped[date | None] = mapped_column(Date)

    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="received", server_default="received", nullable=False, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    patient: Mapped["Patient"] = relationship()
    uploaded_by_user: Mapped["User | None"] = relationship()
    results: Mapped[list["LabResult"]] = relationship(
        back_populates="lab_report",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        back_populates="lab_report",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<LabReport id={self.id!s} patient={self.patient_id!s} status={self.status}>"
