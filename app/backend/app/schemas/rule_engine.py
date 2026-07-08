"""DTOs / result objects for the RuleEngine.

Pydantic v2 models. The RuleEngine is deterministic and non-clinical: it only
compares a structured numeric value against a resolved reference range. Status
uses the approved domain enum `ResultStatus` (no duplicate enum here).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.enums import ResultStatus


class RuleEvaluationInput(BaseModel):
    """Structured input for one parameter evaluation."""

    model_config = ConfigDict(frozen=True)

    parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    raw_value: str | None = None
    normalized_value: Decimal | None = None
    unit: str | None = None
    reference_min: Decimal | None = None
    reference_max: Decimal | None = None
    reference_source: str | None = None
    reference_needs_review: bool = False
    alias_needs_review: bool = False


class RuleEvaluationResult(BaseModel):
    """Deterministic evaluation result (no clinical interpretation)."""

    model_config = ConfigDict(frozen=True)

    parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    status: ResultStatus = ResultStatus.UNKNOWN
    reason: str = ""
    rule_applied: str = ""
    confidence: float = 0.0
    needs_review: bool = True
