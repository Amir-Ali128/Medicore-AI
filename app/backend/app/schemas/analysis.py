"""Schemas used by AliasEngine."""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MatchMethod(StrEnum):
    PARAMETER_CODE = "parameter_code"
    CANONICAL_NAME = "canonical_name"
    NORMALIZED_ALIAS = "normalized_alias"
    FUZZY = "fuzzy"
    UNKNOWN = "unknown"


class AliasCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    parameter_id: uuid.UUID
    parameter_code: str
    canonical_name: str
    similarity: float


class AliasMatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_parameter_name: str
    canonical_parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    canonical_name: str | None = None
    confidence: float = 0.0
    match_method: MatchMethod = MatchMethod.UNKNOWN
    needs_review: bool = True
    alternatives: list[AliasCandidate] = Field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return (
            self.canonical_parameter_id is not None
            and self.match_method != MatchMethod.UNKNOWN
        )

    @classmethod
    def unknown(
        cls,
        raw_parameter_name: str,
        *,
        alternatives: list[AliasCandidate] | None = None,
    ) -> "AliasMatchResult":
        return cls(
            raw_parameter_name=raw_parameter_name,
            confidence=0.0,
            match_method=MatchMethod.UNKNOWN,
            needs_review=True,
            alternatives=alternatives or [],
        )
# --- Reference resolver schemas -----------------------------------------

import uuid as _uuid
from datetime import date as _date
from decimal import Decimal as _Decimal

from pydantic import BaseModel as _BaseModel
from pydantic import ConfigDict as _ConfigDict


class ReferenceResolutionRequest(_BaseModel):
    model_config = _ConfigDict(frozen=True)

    parameter_id: _uuid.UUID | None = None
    parameter_code: str | None = None
    sex: str | None = None
    age_days: int | None = None
    measured_at: _date | None = None
    unit: str | None = None


    @property
    def canonical_parameter_id(self) -> _uuid.UUID | None:
        return self.parameter_id

class ReferenceResolutionResult(_BaseModel):
    model_config = _ConfigDict(frozen=True)

    parameter_id: _uuid.UUID | None = None
    parameter_code: str | None = None
    reference_range_id: _uuid.UUID | None = None
    reference_min: _Decimal | None = None
    reference_max: _Decimal | None = None
    reference_unit: str | None = None
    reference_source: str | None = None
    confidence: float = 0.0
    needs_review: bool = True
    reason: str = ""

    @classmethod
    def needs_review_result(
        cls,
        request: ReferenceResolutionRequest,
        *,
        reason: str = "Reference range requires review.",
    ) -> "ReferenceResolutionResult":
        return cls(
            parameter_id=request.parameter_id,
            parameter_code=request.parameter_code,
            confidence=0.0,
            needs_review=True,
            reason=reason,
        )

# --- Reference resolver schemas -----------------------------------------

import uuid as _uuid
from datetime import date as _date
from decimal import Decimal as _Decimal

from pydantic import BaseModel as _BaseModel
from pydantic import ConfigDict as _ConfigDict


class ReferenceResolutionRequest(_BaseModel):
    model_config = _ConfigDict(frozen=True)

    parameter_id: _uuid.UUID | None = None
    parameter_code: str | None = None
    sex: str | None = None
    age_days: int | None = None
    measured_at: _date | None = None
    unit: str | None = None


    @property
    def canonical_parameter_id(self) -> _uuid.UUID | None:
        return self.parameter_id

class ReferenceResolutionResult(_BaseModel):
    model_config = _ConfigDict(frozen=True)

    parameter_id: _uuid.UUID | None = None
    parameter_code: str | None = None
    reference_range_id: _uuid.UUID | None = None
    reference_min: _Decimal | None = None
    reference_max: _Decimal | None = None
    reference_unit: str | None = None
    reference_source: str | None = None
    confidence: float = 0.0
    needs_review: bool = True
    reason: str = ""

    @classmethod
    def needs_review_result(
        cls,
        request: ReferenceResolutionRequest,
        *,
        reason: str = "Reference range requires review.",
    ) -> "ReferenceResolutionResult":
        return cls(
            parameter_id=request.parameter_id,
            parameter_code=request.parameter_code,
            confidence=0.0,
            needs_review=True,
            reason=reason,
        )

# --- Reference strategy enum --------------------------------------------

from enum import StrEnum as _StrEnum


class ReferenceStrategy(_StrEnum):
    EXACT = "exact"
    DEMOGRAPHIC = "demographic"
    PARAMETER_ONLY = "parameter_only"
    FALLBACK = "fallback"
    UNKNOWN = "unknown"

# --- Reference resolver schemas: final override ---------------------------

import uuid as _ref_uuid
from datetime import date as _ref_date
from decimal import Decimal as _ref_Decimal
from enum import StrEnum as _ref_StrEnum

from pydantic import BaseModel as _ref_BaseModel
from pydantic import ConfigDict as _ref_ConfigDict


class ReferenceStrategy(_ref_StrEnum):
    EXTRACTED = "extracted"
    DATABASE_DEMOGRAPHIC = "database_demographic"
    DATABASE_DEFAULT = "database_default"
    NEEDS_REVIEW = "needs_review"
    UNKNOWN = "unknown"


class ReferenceResolutionRequest(_ref_BaseModel):
    model_config = _ref_ConfigDict(frozen=True)

    parameter_id: _ref_uuid.UUID | None = None
    parameter_code: str | None = None

    sex: str | None = None
    age_days: int | None = None
    measured_at: _ref_date | None = None
    unit: str | None = None

    extracted_reference_min: _ref_Decimal | None = None
    extracted_reference_max: _ref_Decimal | None = None
    extracted_unit: str | None = None
    extracted_reference_source: str | None = None


    @property
    def canonical_parameter_id(self) -> _uuid.UUID | None:
        return self.parameter_id

class ReferenceResolutionResult(_ref_BaseModel):
    model_config = _ref_ConfigDict(frozen=True)

    parameter_id: _ref_uuid.UUID | None = None
    parameter_code: str | None = None

    reference_range_id: _ref_uuid.UUID | None = None
    reference_min: _ref_Decimal | None = None
    reference_max: _ref_Decimal | None = None
    reference_unit: str | None = None
    reference_source: str | None = None

    resolved_from: ReferenceStrategy = ReferenceStrategy.UNKNOWN
    confidence: float = 0.0
    needs_review: bool = True
    reason: str = ""

    @classmethod
    def needs_review_result(
        cls,
        request: ReferenceResolutionRequest,
        *,
        reason: str = "Reference range requires review.",
        **kwargs,
    ) -> "ReferenceResolutionResult":
        return cls(
            parameter_id=request.parameter_id,
            parameter_code=request.parameter_code,
            confidence=0.0,
            needs_review=True,
            reason=reason,
            resolved_from=ReferenceStrategy.NEEDS_REVIEW,
            **kwargs,
        )

