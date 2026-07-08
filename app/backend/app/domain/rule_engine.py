"""RuleEngine.

Deterministic, non-clinical numeric range checker. Given a structured value and
a resolved reference range, it returns one of the approved `ResultStatus` values
(NORMAL / LOW / HIGH / NEEDS_REVIEW / UNKNOWN). It performs no database access,
never calls AI, never diagnoses, and adds no clinical interpretation — it only
compares numbers.

Precedence (first match wins):
    1. unknown parameter               -> UNKNOWN
    2. alias_needs_review              -> NEEDS_REVIEW
    3. reference_needs_review          -> NEEDS_REVIEW
    4. value missing                   -> NEEDS_REVIEW
    5. reference_min/max missing       -> NEEDS_REVIEW
    6. value <  reference_min          -> LOW
    7. value >  reference_max          -> HIGH
    8. min <= value <= max             -> NORMAL   (bounds inclusive)
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import ResultStatus
from app.schemas.rule_engine import RuleEvaluationInput, RuleEvaluationResult

CONF_DETERMINISTIC = 1.0
CONF_REVIEW = 0.0


class RuleEngine:
    """Pure service: one method, no state, no I/O."""

    def evaluate(self, data: RuleEvaluationInput) -> RuleEvaluationResult:
        # 1) Unknown parameter -> cannot evaluate.
        if data.parameter_id is None and not data.parameter_code:
            return self._result(
                data,
                ResultStatus.UNKNOWN,
                rule="unknown_parameter",
                reason="Parameter could not be identified.",
                confidence=CONF_REVIEW,
                needs_review=True,
            )

        # 2) Alias resolution flagged for review.
        if data.alias_needs_review:
            return self._review(
                data,
                rule="alias_needs_review",
                reason="Alias resolution is uncertain; human review required.",
            )

        # 3) Reference resolution flagged for review.
        if data.reference_needs_review:
            return self._review(
                data,
                rule="reference_needs_review",
                reason="Reference range is uncertain; human review required.",
            )

        # 4) Missing measured value.
        if data.normalized_value is None:
            return self._review(
                data,
                rule="missing_value",
                reason="No structured numeric value available.",
            )

        # 5) Missing reference bounds.
        if data.reference_min is None or data.reference_max is None:
            return self._review(
                data,
                rule="missing_reference_bounds",
                reason="Reference minimum and/or maximum is missing.",
            )

        value: Decimal = data.normalized_value
        low: Decimal = data.reference_min
        high: Decimal = data.reference_max

        # 6) Below range.
        if value < low:
            return self._result(
                data,
                ResultStatus.LOW,
                rule="value_below_min",
                reason=f"Value {value} is below reference minimum {low}.",
                confidence=CONF_DETERMINISTIC,
                needs_review=False,
            )

        # 7) Above range.
        if value > high:
            return self._result(
                data,
                ResultStatus.HIGH,
                rule="value_above_max",
                reason=f"Value {value} is above reference maximum {high}.",
                confidence=CONF_DETERMINISTIC,
                needs_review=False,
            )

        # 8) Within range (inclusive bounds).
        return self._result(
            data,
            ResultStatus.NORMAL,
            rule="value_within_range",
            reason=f"Value {value} is within reference range [{low}, {high}].",
            confidence=CONF_DETERMINISTIC,
            needs_review=False,
        )

    # -- helpers ---------------------------------------------------------
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
