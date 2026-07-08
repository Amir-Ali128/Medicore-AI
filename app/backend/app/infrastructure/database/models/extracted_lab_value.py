"""ExtractedLabValue persistence model.

One reviewable value extracted by Claude, prior to deterministic analysis.
String review statuses only (no enums). No business logic in the model.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.extraction_job import ExtractionJob
    from app.infrastructure.database.models.user import User


class ExtractedLabValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "extracted_lab_values"

    extraction_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    raw_parameter_name: Mapped[str | None] = mapped_column(String(255))
    raw_value: Mapped[str | None] = mapped_column(String(128))
    normalized_value: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(String(64))
    extracted_reference_min: Mapped[Decimal | None] = mapped_column(Numeric)
    extracted_reference_max: Mapped[Decimal | None] = mapped_column(Numeric)
    extracted_unit: Mapped[str | None] = mapped_column(String(64))
    measured_at: Mapped[date | None] = mapped_column(Date)

    needs_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    extraction_note: Mapped[str | None] = mapped_column(Text)

    review_status: Mapped[str] = mapped_column(
        String(32),
        default="pending_review",
        server_default="pending_review",
        nullable=False,
        index=True,
    )
    edited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    extraction_job: Mapped["ExtractionJob"] = relationship(
        back_populates="extracted_values"
    )
    edited_by_user: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ExtractedLabValue id={self.id!s} "
            f"name={self.raw_parameter_name!r} review={self.review_status}>"
        )
