"""Reference range model.

A single demographic-scoped normal range for one canonical parameter. The wide,
column-per-demographic source rows (adult male/female, child, elderly, pregnant)
are normalized on import into one row per applicable slice, keyed by `sex`, the
`age_min`/`age_max` window, and `pregnancy_status`.

`reference_min`/`reference_max` use exact NUMERIC to avoid binary-float rounding
on clinical thresholds; a NULL bound denotes an open range (e.g. no upper limit).
This model only stores ranges — it performs no evaluation itself, keeping it
ready for future rule-based numeric validation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import Sex
from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    sex_enum,
)

if TYPE_CHECKING:
    from app.infrastructure.database.models.clinical_parameter import ClinicalParameter


class ReferenceRange(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reference_ranges"

    parameter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_parameters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sex: Mapped[Sex] = mapped_column(
        sex_enum,
        default=Sex.ANY,
        nullable=False,
    )

    # Age window in years; NULL bound = open-ended on that side.
    age_min: Mapped[float | None] = mapped_column(Float)
    age_max: Mapped[float | None] = mapped_column(Float)

    # Tri-state: True (pregnancy-specific), False (non-pregnant), NULL (n/a).
    pregnancy_status: Mapped[bool | None] = mapped_column(Boolean)

    reference_min: Mapped[Decimal | None] = mapped_column(Numeric)
    reference_max: Mapped[Decimal | None] = mapped_column(Numeric)

    unit: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(128))

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    parameter: Mapped["ClinicalParameter"] = relationship(
        back_populates="reference_ranges"
    )

    __table_args__ = (
        CheckConstraint(
            "age_min IS NULL OR age_max IS NULL OR age_min <= age_max",
            name="age_min_le_age_max",
        ),
        CheckConstraint(
            "reference_min IS NULL OR reference_max IS NULL "
            "OR reference_min <= reference_max",
            name="ref_min_le_ref_max",
        ),
        # Primary access path: ranges for a parameter, narrowed by sex.
        Index("ix_reference_ranges_param_sex", "parameter_id", "sex"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ReferenceRange param={self.parameter_id!s} sex={self.sex.value} "
            f"[{self.reference_min}, {self.reference_max}] {self.unit}>"
        )
