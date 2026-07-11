"""Schemas shared by the alias and reference-resolution engines."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import Sex


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


class ReferenceStrategy(StrEnum):
    EXTRACTED = "extracted"
    DATABASE_DEMOGRAPHIC = "database_demographic"
    DATABASE_DEFAULT = "database_default"
    NEEDS_REVIEW = "needs_review"
    UNKNOWN = "unknown"


class ReferenceResolutionRequest(BaseModel):
    """Input expected by ``ReferenceResolver``.

    The previous file defined this model three times. The final definition silently
    discarded ``canonical_parameter_id`` and patient demographics, which prevented
    the resolver from using reference ranges imported from the CSV. Legacy field
    names are normalized here so older callers remain compatible while typos are
    rejected after normalization.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None

    extracted_reference_min: Decimal | None = None
    extracted_reference_max: Decimal | None = None
    extracted_unit: str | None = None
    extracted_reference_source: str | None = None

    patient_age: float | None = None
    patient_sex: Sex | None = None
    pregnancy_status: bool | None = None
    measured_at: date | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)

        if data.get("canonical_parameter_id") is None:
            data["canonical_parameter_id"] = data.get("parameter_id")
        data.pop("parameter_id", None)

        if data.get("patient_sex") is None:
            data["patient_sex"] = data.get("sex")
        data.pop("sex", None)

        if data.get("patient_age") is None:
            for key in ("age", "age_years", "patient_age_years"):
                if data.get(key) is not None:
                    data["patient_age"] = data[key]
                    break

        age_days = data.pop("age_days", None)
        if data.get("patient_age") is None and age_days is not None:
            data["patient_age"] = float(age_days) / 365.25

        for key in ("age", "age_years", "patient_age_years"):
            data.pop(key, None)

        if data.get("pregnancy_status") is None:
            for key in ("pregnant", "is_pregnant"):
                if data.get(key) is not None:
                    data["pregnancy_status"] = data[key]
                    break
        data.pop("pregnant", None)
        data.pop("is_pregnant", None)

        legacy_unit = data.pop("unit", None)
        if data.get("extracted_unit") is None and legacy_unit:
            data["extracted_unit"] = legacy_unit

        return data

    @property
    def parameter_id(self) -> uuid.UUID | None:
        """Backward-compatible alias for older callers."""
        return self.canonical_parameter_id


class ReferenceResolutionResult(BaseModel):
    """Resolved reference range returned to the analysis pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    reference_range_id: uuid.UUID | None = None
    reference_min: Decimal | None = None
    reference_max: Decimal | None = None
    unit: str | None = None
    reference_source: str | None = None
    resolved_from: ReferenceStrategy = ReferenceStrategy.UNKNOWN
    confidence: float = 0.0
    needs_review: bool = True
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)

        if data.get("canonical_parameter_id") is None:
            data["canonical_parameter_id"] = data.get("parameter_id")
        data.pop("parameter_id", None)

        if data.get("unit") is None:
            data["unit"] = data.get("reference_unit")
        data.pop("reference_unit", None)

        return data

    @property
    def parameter_id(self) -> uuid.UUID | None:
        """Backward-compatible alias for older callers."""
        return self.canonical_parameter_id

    @property
    def reference_unit(self) -> str | None:
        """Backward-compatible alias for older API code."""
        return self.unit

    @classmethod
    def needs_review_result(
        cls,
        request: ReferenceResolutionRequest,
        *,
        reason: str = "Reference range requires review.",
        **kwargs: Any,
    ) -> "ReferenceResolutionResult":
        return cls(
            canonical_parameter_id=request.canonical_parameter_id,
            parameter_code=request.parameter_code,
            confidence=0.0,
            needs_review=True,
            reason=reason,
            resolved_from=ReferenceStrategy.NEEDS_REVIEW,
            **kwargs,
        )
