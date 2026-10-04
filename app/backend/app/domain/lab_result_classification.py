"""Deterministic comparison with the reference actually supplied by a report.

Source flags, clinical expectations and generated ranges are never inputs to the
status decision. Censored values are classified only when every possible value
has the same relation to the supplied reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any, Iterable, Literal

Status = Literal["LOW", "NORMAL", "HIGH", "UNKNOWN"]
_NUMBER = r"[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][+-]?\d+)?"
_VALUE = re.compile(rf"^(?P<op><=|>=|<|>)?\s*(?P<value>{_NUMBER})$")
_RANGE = re.compile(
    rf"^(?P<low>{_NUMBER})\s*[-‐‑‒–—−]\s*(?P<high>{_NUMBER})(?:\s*(?P<unit>\S.*))?$"
)
_LIMIT = re.compile(rf"^(?P<op><=|>=|<|>)\s*(?P<value>{_NUMBER})(?:\s*(?P<unit>\S.*))?$")
_UNSAFE_REASON = re.compile(
    r"conflict|missing_parameter|missing_observed|invalid_reference|"
    r"reference_unit_mismatch|invalid_numeric|low_input_confidence"
)


@dataclass(frozen=True)
class LabClassification:
    status: Status
    reference_low: float | None
    reference_high: float | None
    raw_reference: str | None
    classification_reason: str


@dataclass(frozen=True)
class _Interval:
    low: Decimal | None
    high: Decimal | None
    low_inclusive: bool = True
    high_inclusive: bool = True


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace("−", "-")
    if not re.fullmatch(_NUMBER, text):
        return None
    try:
        result = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None
    return result if result.is_finite() and math.isfinite(float(result)) else None


def normalize_lab_unit(value: str | None) -> str | None:
    """Compare typographic aliases, without performing unit conversion."""
    if not value or not str(value).strip():
        return None
    # Typography aliases only. Never silently convert different measurement units.
    return re.sub(r"\s+", "", str(value)).casefold().replace("µ", "u").replace("μ", "u")


def _subset(observed: _Interval, target: _Interval) -> bool:
    if target.low is not None:
        if observed.low is None or observed.low < target.low:
            return False
        if observed.low == target.low and observed.low_inclusive and not target.low_inclusive:
            return False
    if target.high is not None:
        if observed.high is None or observed.high > target.high:
            return False
        if observed.high == target.high and observed.high_inclusive and not target.high_inclusive:
            return False
    return True


def classify_lab_result(
    *,
    value: Any,
    unit: str | None = None,
    reference_text: str | None = None,
    reference_low: Any = None,
    reference_high: Any = None,
    reference_unit: str | None = None,
    ingestion_reasons: Iterable[Any] | None = (),
) -> LabClassification:
    """Return source-preserving status; numeric structured references are optional.

The caller must first select any age/sex-specific source reference. Structured
bounds can represent that selected row even when its text includes a demographic
label. If plain numeric reference text is present, its bounds must agree with the
structured bounds. No source flag or incoming status can override comparison.
"""
    raw_reference = reference_text
    text = str(reference_text or "").strip().replace("≤", "<=").replace("≥", ">=").replace("−", "-")
    low, high = _number(reference_low), _number(reference_high)
    lower_inclusive = upper_inclusive = True
    text_unit = None

    def result(status: Status, reason: str) -> LabClassification:
        return LabClassification(
            status=status,
            reference_low=float(low) if low is not None else None,
            reference_high=float(high) if high is not None else None,
            raw_reference=raw_reference,
            classification_reason=reason,
        )

    if (reference_low is not None and low is None) or (reference_high is not None and high is None):
        return result("UNKNOWN", "invalid_reference_bounds")

    # A selected demographic row may include a label before its numeric range.
    # Preserve a printed strict comparator instead of assuming an inclusive bound.
    comparable = text.rsplit(":", 1)[-1].strip() if (low is not None or high is not None) else text
    range_match, limit_match = _RANGE.fullmatch(comparable), _LIMIT.fullmatch(comparable)
    if range_match:
        parsed_low, parsed_high = _number(range_match["low"]), _number(range_match["high"])
        if (low is not None and low != parsed_low) or (high is not None and high != parsed_high):
            return result("UNKNOWN", "reference_bounds_conflict")
        low, high = parsed_low, parsed_high
        text_unit = range_match["unit"]
    elif limit_match:
        limit, comparator = _number(limit_match["value"]), limit_match["op"]
        if comparator.startswith("<"):
            if low is not None or (high is not None and high != limit):
                return result("UNKNOWN", "reference_bounds_conflict")
            high = limit
            upper_inclusive = comparator == "<="
        else:
            if high is not None or (low is not None and low != limit):
                return result("UNKNOWN", "reference_bounds_conflict")
            low = limit
            lower_inclusive = comparator == ">="
        text_unit = limit_match["unit"]

    if low is not None and high is not None and low > high:
        return result("UNKNOWN", "invalid_reference_bounds")
    if low is None and high is None:
        return result("UNKNOWN", "missing_numeric_reference")

    measured_unit = normalize_lab_unit(unit)
    supplied_units = {normalize_lab_unit(item) for item in (reference_unit, text_unit) if normalize_lab_unit(item)}
    if supplied_units and (len(supplied_units) != 1 or measured_unit not in supplied_units):
        return result("UNKNOWN", "reference_unit_mismatch")

    reasons = (ingestion_reasons,) if isinstance(ingestion_reasons, str) else (ingestion_reasons or ())
    if any(_UNSAFE_REASON.search(str(reason)) for reason in reasons):
        return result("UNKNOWN", "ingestion_review_required")

    match = _VALUE.fullmatch(str(value).strip().replace("≤", "<=").replace("≥", ">=").replace("−", "-"))
    if isinstance(value, bool) or match is None:
        return result("UNKNOWN", "invalid_observed_value")
    number = _number(match["value"])
    if number is None:
        return result("UNKNOWN", "invalid_observed_value")
    comparator = match["op"]
    if comparator in ("<", "<="):
        observed = _Interval(None, number, high_inclusive=comparator == "<=")
    elif comparator in (">", ">="):
        observed = _Interval(number, None, low_inclusive=comparator == ">=")
    else:
        observed = _Interval(number, number)

    normal = _Interval(low, high, lower_inclusive, upper_inclusive)
    if low is not None and _subset(observed, _Interval(None, low, high_inclusive=not lower_inclusive)):
        return result("LOW", "below_source_reference")
    if high is not None and _subset(observed, _Interval(high, None, low_inclusive=not upper_inclusive)):
        return result("HIGH", "above_source_reference")
    if _subset(observed, normal):
        return result("NORMAL", "within_source_reference")
    return result("UNKNOWN", "ambiguous_censored_value")
