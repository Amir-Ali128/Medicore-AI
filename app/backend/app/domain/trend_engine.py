"""TrendEngine.

Pure, deterministic numeric-movement describer. Given a current and a previous
value (plus optional dates), it reports one of the approved `TrendStatus` values
(UP / DOWN / STABLE / NO_PREVIOUS_RESULT). It never diagnoses and adds no
clinical meaning — it only describes movement.

Invalid or non-numeric input yields NO_PREVIOUS_RESULT with needs_review=True
and a clear reason (there is no separate review status in the domain enum).

If the previous value is passed in, no database access is required, keeping this
a fully testable pure service.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domain.enums import TrendStatus
from app.schemas.trend import TrendComparisonInput, TrendResult

# Movement at/under this relative magnitude is treated as STABLE (noise band).
STABLE_RELATIVE_THRESHOLD = 0.05  # 5%
CONF_WITH_DATES = 1.0
CONF_WITHOUT_DATES = 0.8
CONF_NONE = 0.0


class TrendEngine:
    """Pure service: describes numeric movement, nothing more."""

    def compare(self, data: TrendComparisonInput) -> TrendResult:
        # No previous measurement to compare against.
        if data.previous_value is None:
            return self._base(
                data,
                TrendStatus.NO_PREVIOUS_RESULT,
                confidence=CONF_NONE,
                reason="No previous result available for comparison.",
            )

        # Current/previous value missing or non-numeric -> cannot describe
        # movement. Domain enum has no review status, so report
        # NO_PREVIOUS_RESULT and flag for review.
        current = self._to_decimal(data.current_value)
        previous = self._to_decimal(data.previous_value)
        if current is None or previous is None:
            return self._base(
                data,
                TrendStatus.NO_PREVIOUS_RESULT,
                confidence=CONF_NONE,
                reason="Current and/or previous value is missing or non-numeric.",
                needs_review=True,
            )

        absolute_difference = current - previous
        percentage_difference = self._percentage(previous, absolute_difference)
        time_difference_days = self._days_between(data)

        status = self._classify(absolute_difference, percentage_difference)
        confidence = CONF_WITH_DATES if time_difference_days is not None else CONF_WITHOUT_DATES

        return TrendResult(
            parameter_id=data.parameter_id,
            parameter_code=data.parameter_code,
            trend_status=status,
            previous_value=previous,
            current_value=current,
            absolute_difference=absolute_difference,
            percentage_difference=percentage_difference,
            time_difference_days=time_difference_days,
            confidence=confidence,
            reason=self._reason(status, absolute_difference, percentage_difference),
            needs_review=False,
        )

    # -- internals -------------------------------------------------------
    def _classify(
        self,
        absolute_difference: Decimal,
        percentage_difference: float | None,
    ) -> TrendStatus:
        if absolute_difference == 0:
            return TrendStatus.STABLE

        # Relative noise band when a baseline exists.
        if percentage_difference is not None:
            if abs(percentage_difference) <= STABLE_RELATIVE_THRESHOLD * 100:
                return TrendStatus.STABLE

        return TrendStatus.UP if absolute_difference > 0 else TrendStatus.DOWN

    @staticmethod
    def _percentage(previous: Decimal, absolute_difference: Decimal) -> float | None:
        if previous == 0:
            return None
        return float(absolute_difference / previous * Decimal(100))

    @staticmethod
    def _days_between(data: TrendComparisonInput) -> int | None:
        if data.current_date is None or data.previous_date is None:
            return None
        return (data.current_date - data.previous_date).days

    @staticmethod
    def _to_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _reason(
        status: TrendStatus,
        absolute_difference: Decimal,
        percentage_difference: float | None,
    ) -> str:
        pct = (
            f" ({percentage_difference:+.2f}%)"
            if percentage_difference is not None
            else ""
        )
        if status == TrendStatus.STABLE:
            return f"Change {absolute_difference:+}{pct} is within the stable band."
        if status == TrendStatus.UP:
            return f"Value increased by {absolute_difference:+}{pct}."
        if status == TrendStatus.DOWN:
            return f"Value decreased by {absolute_difference:+}{pct}."
        return ""

    @staticmethod
    def _base(
        data: TrendComparisonInput,
        status: TrendStatus,
        *,
        confidence: float,
        reason: str,
        needs_review: bool = False,
    ) -> TrendResult:
        return TrendResult(
            parameter_id=data.parameter_id,
            parameter_code=data.parameter_code,
            trend_status=status,
            previous_value=data.previous_value if isinstance(data.previous_value, Decimal) else None,
            current_value=data.current_value if isinstance(data.current_value, Decimal) else None,
            absolute_difference=None,
            percentage_difference=None,
            time_difference_days=None,
            confidence=confidence,
            reason=reason,
            needs_review=needs_review,
        )
