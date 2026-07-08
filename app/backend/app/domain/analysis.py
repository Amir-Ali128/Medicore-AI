"""DTOs / result objects for alias and reference-range resolution.

Pydantic v2 models shared by `AliasEngine` and `ReferenceResolver`. These carry
*only* resolution outputs — they do not compare measured values, classify
results, or produce any clinical judgement.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Sex


class MatchMethod(StrEnum):
    """How an alias match was obtained (in resolution-priority order)."""

    PARAMETER_CODE = "parameter_code"
    CANONICAL_NAME = "canonical_name"
    NORMALIZED_ALIAS = "normalized_alias"
    FUZZY = "fuzzy"
    NONE = "none"


class ReferenceStrategy(StrEnum):
    """Which tier produced the resolved reference range."""

    EXTRACTED = "extracted"
    DATABASE_DEMOGRAPHIC = "database_demographic"
    DATABASE_DEFAULT = "database_default"
    NEEDS_REVIEW = "needs_review"


# --------------------------------------------------------------------------
# Alias resolution
# --------------------------------------------------------------------------
class AliasCandidate(BaseModel):
    """A near-match surfaced for human review (fuzzy path)."""

    model_config = ConfigDict(frozen=True)

    parameter_id: uuid.UUID
    parameter_code: str
    canonical_name: str
    similarity: float


class AliasMatchResult(BaseModel):
    """Outcome of resolving a raw parameter name to a canonical parameter."""

    model_config = ConfigDict(frozen=True)

    raw_parameter_name: str
    canonical_parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    canonical_name: str | None = None
    confidence: float = 0.0
    match_method: MatchMethod = MatchMethod.NONE
    needs_review: bool = True
    alternatives: list[AliasCandidate] = Field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return self.canonical_parameter_id is not None

    @classmethod
    def unknown(
        cls,
        raw_parameter_name: str,
        alternatives: list[AliasCandidate] | None = None,
    ) -> "AliasMatchResult":
        return cls(
            raw_parameter_name=raw_parameter_name,
            match_method=MatchMethod.NONE,
            confidence=0.0,
            needs_review=True,
            alternatives=alternatives or [],
        )


# --------------------------------------------------------------------------
# Reference-range resolution
# --------------------------------------------------------------------------
class ReferenceResolutionRequest(BaseModel):
    """Inputs for resolving which reference range applies."""

    model_config = ConfigDict(frozen=True)

    canonical_parameter_id: uuid.UUID
    extracted_reference_min: Decimal | None = None
    extracted_reference_max: Decimal | None = None
    extracted_unit: str | None = None
    patient_age: float | None = None
    patient_sex: Sex | None = None
    pregnancy_status: bool | None = None


class ReferenceResolutionResult(BaseModel):
    """Resolved reference range plus provenance (no value comparison)."""

    model_config = ConfigDict(frozen=True)

    canonical_parameter_id: uuid.UUID
    reference_min: Decimal | None = None
    reference_max: Decimal | None = None
    unit: str | None = None
    reference_source: str | None = None
    confidence: float = 0.0
    reason: str = ""
    needs_review: bool = True
    resolved_from: ReferenceStrategy = ReferenceStrategy.NEEDS_REVIEW

    @classmethod
    def needs_review_result(
        cls, canonical_parameter_id: uuid.UUID, reason: str
    ) -> "ReferenceResolutionResult":
        return cls(
            canonical_parameter_id=canonical_parameter_id,
            reason=reason,
            confidence=0.0,
            needs_review=True,
            resolved_from=ReferenceStrategy.NEEDS_REVIEW,
        )
