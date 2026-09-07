"""RuleEngine.

Deterministic, non-clinical numeric range checker. Production execution prefers the
native C++ deterministic core; the Python implementation remains a compatibility
fallback for dev/rolling deploys where the extension is not installed.
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import ResultStatus
from app.schemas.rule_engine import RuleEvaluationInput, RuleEvaluationResult

CONF_DETERMINISTIC = 1.0
CONF_REVIEW = 0.0


class RuleEngine:
    """Pure service: native C++ first, behavior-compatible Python fallback."""

    def evaluate(self, data: RuleEvaluationInput) -> RuleEvaluationResult:
        try:
            from app.domain.native_lab_engine import (
                native_evaluate_rule,
                native_lab_deterministic_available,
            )

            if native_lab_deterministic_available():
                native = native_evaluate_rule(
                    parameter_known=bool(data.parameter_id is not None or data.parameter_code),
                    alias_needs_review=data.alias_needs_review,
                    reference_needs_review=data.reference_needs_review,
                    normalized_value=data.normalized_value,
                    reference_min=data.reference_min,
                    reference_max=data.reference_max,
                )
                return RuleEvaluationResult(
                    parameter_id=data.parameter_id,
                    parameter_code=data.parameter_code,
                    status=ResultStatus(str(native["status"]).lower()),
                    reason=str(native.get("reason") or ""),
                    rule_applied=str(native.get("rule_applied") or ""),
                    confidence=float(native.get("confidence") or 0.0),
                    needs_review=bool(native.get("needs_review")),
                )
        except (ImportError, RuntimeError, OSError, ValueError, KeyError):
            pass

        return self._evaluate_python(data)

    def _evaluate_python(self, data: RuleEvaluationInput) -> RuleEvaluationResult:
        if data.parameter_id is None and not data.parameter_code:
            return self._result(
                data,
                ResultStatus.UNKNOWN,
                rule="unknown_parameter",
                reason="Parameter could not be identified.",
                confidence=CONF_REVIEW,
                needs_review=True,
            )

        if data.alias_needs_review:
            return self._review(
                data,
                rule="alias_needs_review",
                reason="Alias resolution is uncertain; human review required.",
            )

        if data.reference_needs_review:
            return self._review(
                data,
                rule="reference_needs_review",
                reason="Reference range is uncertain; human review required.",
            )

        if data.normalized_value is None:
            return self._review(
                data,
                rule="missing_value",
                reason="No structured numeric value available.",
            )

        if data.reference_min is None or data.reference_max is None:
            return self._review(
                data,
                rule="missing_reference_bounds",
                reason="Reference minimum and/or maximum is missing.",
            )

        value: Decimal = data.normalized_value
        low: Decimal = data.reference_min
        high: Decimal = data.reference_max

        if low > high:
            return self._review(
                data,
                rule="invalid_reference_range",
                reason="Reference minimum is greater than reference maximum.",
            )

        if value < low:
            return self._result(
                data,
                ResultStatus.LOW,
                rule="value_below_min",
                reason=f"Value {value} is below reference minimum {low}.",
                confidence=CONF_DETERMINISTIC,
                needs_review=False,
            )

        if value > high:
            return self._result(
                data,
                ResultStatus.HIGH,
                rule="value_above_max",
                reason=f"Value {value} is above reference maximum {high}.",
                confidence=CONF_DETERMINISTIC,
                needs_review=False,
            )

        return self._result(
            data,
            ResultStatus.NORMAL,
            rule="value_within_range",
            reason=f"Value {value} is within reference range [{low}, {high}].",
            confidence=CONF_DETERMINISTIC,
            needs_review=False,
        )

    @staticmethod
    def _result(
        data: RuleEvaluationInput,
        status: ResultStatus,
        *,
        rule: str,
        reason: str,
        confidence: float,
        needs_review: bool,
    ) -> RuleEvaluationResult:
        return RuleEvaluationResult(
            parameter_id=data.parameter_id,
            parameter_code=data.parameter_code,
            status=status,
            reason=reason,
            rule_applied=rule,
            confidence=confidence,
            needs_review=needs_review,
        )

    @classmethod
    def _review(
        cls, data: RuleEvaluationInput, *, rule: str, reason: str
    ) -> RuleEvaluationResult:
        return cls._result(
            data,
            ResultStatus.NEEDS_REVIEW,
            rule=rule,
            reason=reason,
            confidence=CONF_REVIEW,
            needs_review=True,
        )
