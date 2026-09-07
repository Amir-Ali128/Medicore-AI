"""TrendEngine.

Pure, deterministic numeric-movement describer. Production execution prefers the
native C++ deterministic core; the Decimal-based Python implementation remains as a
behavior-compatible fallback for dev/rolling deploys.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domain.enums import TrendStatus
from app.schemas.trend import TrendComparisonInput, TrendResult

STABLE_RELATIVE_THRESHOLD = 0.05
CONF_WITH_DATES = 1.0
CONF_WITHOUT_DATES = 0.8
CONF_NONE = 0.0


class TrendEngine:
    """Pure service: describes numeric movement, nothing more."""

    def compare(self, data: TrendComparisonInput) -> TrendResult:
        native = self._compare_native(data)
        if native is not None:
            return native
        return self._compare_python(data)

    def _compare_native(self, data: TrendComparisonInput) -> TrendResult | None:
        try:
            from app.domain.native_lab_engine import (
                native_compare_trend,
                native_lab_deterministic_available,
            )

            if not native_lab_deterministic_available():
                return None

            days = self._days_between(data)
            result = native_compare_trend(
                current_value=data.current_value,
                previous_value=data.previous_value,
                time_difference_days=days,
                stable_relative_threshold=STABLE_RELATIVE_THRESHOLD,
            )
            return TrendResult(
                parameter_id=data.parameter_id,
                parameter_code=data.parameter_code,
                trend_status=TrendStatus(str(result["status"]).lower()),
                previous_value=self._to_decimal(result.get("previous_value")),
                current_value=self._to_decimal(result.get("current_value")),
                absolute_difference=self._to_decimal(result.get("absolute_difference")),
                percentage_difference=result.get("percentage_difference"),
                time_difference_days=result.get("time_difference_days"),
                confidence=float(result.get("confidence") or 0.0),
                reason=str(result.get("reason") or ""),
                needs_review=bool(result.get("needs_review")),
            )
        except (ImportError, RuntimeError, OSError, ValueError, KeyError, TypeError):
            return None

    def _compare_python(self, data: TrendComparisonInput) -> TrendResult:
        if data.previous_value is None:
            return self._base(
                data,
                TrendStatus.NO_PREVIOUS_RESULT,
                confidence=CONF_NONE,
                reason="No previous result available for comparison.",
            )

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

    def _classify(
        self,
        absolute_difference: Decimal,
        percentage_difference: float | None,
    ) -> TrendStatus:
        if absolute_difference == 0:
            return TrendStatus.STABLE
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
