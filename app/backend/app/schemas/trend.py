"""DTOs / result objects for the TrendEngine.

Pydantic v2 models. The TrendEngine only describes numeric movement between a
current and a previous value. Direction uses the approved domain enum
`TrendStatus` (no duplicate enum here). Invalid/non-numeric input is reported as
NO_PREVIOUS_RESULT with needs_review=True and a clear reason.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.domain.enums import TrendStatus


class TrendComparisonInput(BaseModel):
    """Input for comparing a current result with a previous one."""

    model_config = ConfigDict(frozen=True)

    parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    current_value: Decimal | None = None
    previous_value: Decimal | None = None
    current_date: date | None = None
    previous_date: date | None = None


class TrendResult(BaseModel):
    """Numeric-movement description (no clinical meaning)."""

    model_config = ConfigDict(frozen=True)

    parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    trend_status: TrendStatus = TrendStatus.NO_PREVIOUS_RESULT
    previous_value: Decimal | None = None
    current_value: Decimal | None = None
    absolute_difference: Decimal | None = None
    percentage_difference: float | None = None
    time_difference_days: int | None = None
    confidence: float = 0.0
    reason: str = ""
    needs_review: bool = False
