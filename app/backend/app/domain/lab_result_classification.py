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
from app.domain.consistency_config import ANNOTATION_ONLY_CODES, ANNOTATION_FEATURES

Status = Literal["LOW", "NORMAL", "HIGH", "UNKNOWN"]
_NUMBER = r"[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][+-]?\d+)?"
_VALUE = re.compile(rf"^(?P<op><=|>=|<|>)?\s*(?P<value>{_NUMBER})(?:\s+(?P<unit>\S.*))?$")
_RANGE = re.compile(
    rf"^(?P<low>{_NUMBER})\s*[-‐‑‒–—−]\s*(?P<high>{_NUMBER})(?:\s*(?P<unit>\S.*))?$"
)
_LIMIT = re.compile(rf"^(?P<op><=|>=|<|>)\s*(?P<value>{_NUMBER})(?:\s*(?P<unit>\S.*))?$")
_UNSAFE_REASON = re.compile(
    r"conflict|missing_parameter|missing_observed|invalid_reference|"
    r"reference_unit_mismatch|observed_unit_mismatch|unverified_observed_unit|invalid_numeric|low_input_confidence"
)


@dataclass(frozen=True)
class LabClassification:
    status: Status
    reference_low: float | None
    reference_high: float | None
    raw_reference: str | None
    classification_reason: str
    normalized_value: float | None = None
    value_comparator: str | None = None
    value_limit: float | None = None
    parsed_unit: str | None = None


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
    text = re.sub(r"\s+", "", str(value)).casefold().replace("µ", "u").replace("μ", "u")
    # x/× and superscripts spell the unit scale; no measured value is rescaled.
    text = re.sub(r'^x(?=10)', '', text).replace('×10', '10')
    superscripts = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')
    return re.sub(r'10([⁰¹²³⁴⁵⁶⁷⁸⁹]+)', lambda match: '10^'+match[1].translate(superscripts), text)


# Physical unit spellings only; this list supplies no medical reference values.
_INLINE_UNITS = frozenset(normalize_lab_unit(value) for value in (
    '%', 'mg/L', 'mg/dL', 'g/L', 'g/dL', 'ng/mL', 'ng/L', 'pg/mL', 'pg',
    'ug/L', 'ug/dL', 'ug/mL', 'mmol/L', 'umol/L', 'mEq/L', 'mol/L',
    'U/L', 'IU/L', 'U/mL', 'IU/mL', 'mIU/L', 'uIU/mL', 'mU/L',
    '10^9/L', '10^12/L', '10^3/uL', '10^6/uL', '10³/uL', '10⁶/uL',
    '10⁹/L', '10¹²/L', '/uL', 'cells/uL', 'fL', 'mm/h', 'mm/s', 'mm/saat',
    'mL/min', 'mL/min/1.73m2', 'mL/min/1.73m²', 'mmHg',
))


@dataclass(frozen=True)
class ParsedObservation:
    number: Decimal | None
    comparator: str | None = None
    inline_unit: str | None = None
    error: str | None = None


def parse_lab_observation(value: Any, unit: str | None = None) -> ParsedObservation:
    text = str(value).strip().replace('≤', '<=').replace('≥', '>=').replace('−', '-')
    prefix_percent = re.fullmatch(rf'(?P<op><=|>=|<|>)?\s*%\s*(?P<value>{_NUMBER})', text)
    if prefix_percent:
        text = (prefix_percent['op'] or '') + prefix_percent['value'] + ' %'
    match = _VALUE.fullmatch(text)
    if isinstance(value, bool) or match is None or _number(match['value']) is None:
        return ParsedObservation(None, error='invalid_observed_value')
    inline = match['unit']
    if inline:
        normalized = normalize_lab_unit(inline)
        if normalized not in _INLINE_UNITS:
            return ParsedObservation(None, error='unverified_observed_unit')
        if normalize_lab_unit(unit) and normalize_lab_unit(unit) != normalized:
            return ParsedObservation(None, error='observed_unit_mismatch')
    return ParsedObservation(_number(match['value']), match['op'], inline)


@dataclass(frozen=True)
class ParsedReference:
    low: Decimal | None
    high: Decimal | None
    low_inclusive: bool = True
    high_inclusive: bool = True
    unit: str | None = None
    error: str | None = None


def parse_source_reference(text: str | None, minimum: Any = None, maximum: Any = None) -> ParsedReference:
    raw = str(text or '').strip().replace('≤', '<=').replace('≥', '>=').replace('−', '-')
    low, high = _number(minimum), _number(maximum)
    if (minimum is not None and low is None) or (maximum is not None and high is None):
        return ParsedReference(low, high, error='invalid_reference_bounds')
    # Generic report labels are safe to remove without demographic inference.
    comparable = re.sub(r'^(?:ref(?:erence)?(?:\s+range)?|referans(?:\s+aral[iı]ğ[iı])?|normal(?:\s+range)?)\s*:\s*', '', raw, flags=re.I)
    if comparable == raw and (low is not None or high is not None):
        # The caller selected the structured age/sex row before arriving here.
        comparable = raw.rsplit(':', 1)[-1].strip()
    interval, limit = _RANGE.fullmatch(comparable), _LIMIT.fullmatch(comparable)
    li = hi = True
    suffix = None
    if interval:
        a, b = _number(interval['low']), _number(interval['high'])
        if a is None or b is None:
            return ParsedReference(low, high, error='invalid_reference_bounds')
        if (low is not None and low != a) or (high is not None and high != b):
            return ParsedReference(low, high, error='reference_bounds_conflict')
        low, high, suffix = a, b, interval['unit']
    elif limit:
        number, op, suffix = _number(limit['value']), limit['op'], limit['unit']
        if number is None:
            return ParsedReference(low, high, error='invalid_reference_bounds')
        if op.startswith('<'):
            if low is not None or (high is not None and high != number):
                return ParsedReference(low, high, error='reference_bounds_conflict')
            high, hi = number, op == '<='
        else:
            if high is not None or (low is not None and low != number):
                return ParsedReference(low, high, error='reference_bounds_conflict')
            low, li = number, op == '>='
    elif raw:
        return ParsedReference(low, high, error='invalid_reference_text' if low is not None or high is not None else 'missing_numeric_reference')
    if low is not None and high is not None and low > high:
        return ParsedReference(low, high, error='invalid_reference_bounds')
    if low is None and high is None:
        return ParsedReference(low, high, error='missing_numeric_reference')
    return ParsedReference(low, high, li, hi, suffix)


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
    reference = parse_source_reference(reference_text, reference_low, reference_high)
    low, high = reference.low, reference.high
    lower_inclusive, upper_inclusive = reference.low_inclusive, reference.high_inclusive
    text_unit = reference.unit
    observation = parse_lab_observation(value, unit)

    def result(status: Status, reason: str) -> LabClassification:
        numeric = float(observation.number) if observation.number is not None else None
        return LabClassification(
            status=status,
            reference_low=float(low) if low is not None else None,
            reference_high=float(high) if high is not None else None,
            raw_reference=raw_reference,
            classification_reason=reason,
            normalized_value=numeric if observation.comparator is None else None,
            value_comparator=observation.comparator,
            value_limit=numeric if observation.comparator else None,
            parsed_unit=(unit if normalize_lab_unit(unit) else observation.inline_unit) if not observation.error else None,
        )

    if reference.error:
        return result('UNKNOWN', reference.error)

    measured_unit = normalize_lab_unit(unit) or normalize_lab_unit(observation.inline_unit)
    supplied_units = {normalize_lab_unit(item) for item in (reference_unit, text_unit) if normalize_lab_unit(item)}
    if supplied_units and (len(supplied_units) != 1 or measured_unit not in supplied_units):
        return result("UNKNOWN", "reference_unit_mismatch")

    reasons = (ingestion_reasons,) if isinstance(ingestion_reasons, str) else (ingestion_reasons or ())
    from app.core.config import get_settings
    annotation_active = any(getattr(get_settings(), name, False) for name in ANNOTATION_FEATURES)
    if any(not (annotation_active and str(reason) in ANNOTATION_ONLY_CODES) and _UNSAFE_REASON.search(str(reason)) for reason in reasons):
        return result("UNKNOWN", "ingestion_review_required")

    if observation.error or observation.number is None:
        return result('UNKNOWN', observation.error or 'invalid_observed_value')
    number, comparator = observation.number, observation.comparator
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
