"""DoctorReview persistence model.

A physician's action on a clinical hypothesis. Holds the review action, optional
edits, requested tests, and referral. No business logic lives in the model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import ReviewAction
from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    review_action_enum,
)

if TYPE_CHECKING:
    from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
    from app.infrastructure.database.models.user import User


class DoctorReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doctor_reviews"

    clinical_hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_hypotheses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    action: Mapped[ReviewAction] = mapped_column(review_action_enum, nullable=False)
    doctor_note: Mapped[str | None] = mapped_column(Text)
    edited_title: Mapped[str | None] = mapped_column(String(255))
    edited_summary: Mapped[str | None] = mapped_column(Text)
    requested_tests_json: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    specialist_referral: Mapped[str | None] = mapped_column(String(128))

    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    clinical_hypothesis: Mapped["ClinicalHypothesis"] = relationship(
        back_populates="doctor_reviews"
    )
    doctor: Mapped["User"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<DoctorReview id={self.id!s} hypothesis={self.clinical_hypothesis_id!s} "
            f"action={self.action.value}>"
        )
