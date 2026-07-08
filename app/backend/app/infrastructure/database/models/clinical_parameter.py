"""Canonical clinical (laboratory) parameter model.

The single source of truth for a normalized lab test. Every parameter from the
reference CSV is imported here; only Phase 1 groups are marked
`active_phase1=True` with `analysis_level=L4`. All other parameters are stored
as passive dictionary records (`active_phase1=False`, `analysis_level=L0`):
recognizable and listable, but excluded from active Phase 1 analysis.

Extra, less-structured attributes from the source data (clinical meanings,
interpretation thresholds, assay notes, unit-system variants, provenance, ...)
are preserved in `metadata_json` rather than widening the schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Index, String, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums import AnalysisLevel
from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    analysis_level_enum,
)

if TYPE_CHECKING:
    from app.infrastructure.database.models.parameter_alias import ParameterAlias
    from app.infrastructure.database.models.reference_range import ReferenceRange


class ClinicalParameter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "clinical_parameters"

    canonical_name: Mapped[str] = mapped_column(
        String(255), index=True, nullable=False
    )
    parameter_code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    default_unit: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(128), index=True)

    active_phase1: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, index=True
    )
    analysis_level: Mapped[AnalysisLevel] = mapped_column(
        analysis_level_enum,
        default=AnalysisLevel.L0,
        nullable=False,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    # --- Relationships ---------------------------------------------------
    aliases: Mapped[list["ParameterAlias"]] = relationship(
        back_populates="canonical_parameter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reference_ranges: Mapped[list["ReferenceRange"]] = relationship(
        back_populates="parameter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # Fast lookup of active Phase 1 parameters filtered by category.
        Index("ix_clinical_parameters_phase1_category", "active_phase1", "category"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<ClinicalParameter code={self.parameter_code!r} "
            f"active_phase1={self.active_phase1} level={self.analysis_level.value}>"
        )
