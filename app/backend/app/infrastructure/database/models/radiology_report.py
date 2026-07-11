"""Radiology report persistence model for Phase 2 text analysis."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.patient import Patient
    from app.infrastructure.database.models.user import User


class RadiologyReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "radiology_reports"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(64), default="manual", server_default="manual", nullable=False
    )
    file_name: Mapped[str | None] = mapped_column(String(512))
    report_date: Mapped[date | None] = mapped_column(Date, index=True)
    modality: Mapped[str] = mapped_column(
        String(32), default="UNKNOWN", server_default="UNKNOWN", nullable=False, index=True
    )
    body_part: Mapped[str] = mapped_column(
        String(64), default="OTHER", server_default="OTHER", nullable=False, index=True
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    findings_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    measurements_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    critical_findings_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    impression: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="analyzed", server_default="analyzed", nullable=False, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    patient: Mapped["Patient"] = relationship()
    uploaded_by_user: Mapped["User | None"] = relationship()
