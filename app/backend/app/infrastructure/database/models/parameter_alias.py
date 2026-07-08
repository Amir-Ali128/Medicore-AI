"""Parameter alias model.

Maps a raw/observed lab test name to its canonical parameter. `normalized_alias`
holds the lookup key (e.g. case-folded, punctuation-stripped) and is indexed so
incoming raw names can be resolved quickly. `confidence` supports probabilistic
or curated mappings; `source` records provenance (e.g. CSV, manual review).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.infrastructure.database.models.clinical_parameter import ClinicalParameter


class ParameterAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "parameter_aliases"

    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(
        String(255), index=True, nullable=False
    )

    canonical_parameter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_parameters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str | None] = mapped_column(String(128))

    canonical_parameter: Mapped["ClinicalParameter"] = relationship(
        back_populates="aliases"
    )

    __table_args__ = (
        UniqueConstraint(
            "canonical_parameter_id",
            "normalized_alias",
            name="parameter_alias_param_normalized",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_between_0_and_1",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ParameterAlias alias={self.alias!r} "
            f"-> {self.canonical_parameter_id!s} conf={self.confidence}>"
        )
