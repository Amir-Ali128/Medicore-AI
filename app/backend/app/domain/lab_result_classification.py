"""Deterministic comparison with the reference actually supplied by a report.

Source flags, clinical expectations and generated ranges are never inputs to the
status decision. Censored values are classified only when every possible value
has the same relation to the supplied reference.

Parsing rules (all source-preserving, nothing is invented):

* Numbers: "3,5" and "3.5" are decimals; "1.234,5" is Turkish thousands +
  decimal comma; "250.000" is read as 250000 only when the row's unit is a
  count per volume (/µL, /mm³, hücre/µL) or the same row mixes grouped tokens
  with plain 4+ digit integers. Otherwise it keeps its decimal meaning
  (urine density "1.038" is a real decimal).
* References: "3,5 - 5,1", "3.5 – 5.1", "(3.5-5.1)", "0.5-1.5 mg/dL", "< 200",
  "<=5", "≤ 5", "-2 / +2", "Ref: 4-10" are parsed. Sex-specific text such as
  "Erkek: 13-17 Kadın: 12-15" or "> 40 (kadın > 50)" is resolved only with a
  known patient sex; otherwise it stays UNKNOWN with an explanation.
  Ambiguous text ("40 >", "Adult: 2-5", "2-5 or 8-10") stays UNKNOWN.
* Units: only factor-1 spellings are aliased (K/µL ≡ 10³/µL ≡ 10^9/L,
  µIU/mL ≡ mIU/L, mm/saat ≡ mm/h). Units with different magnitudes are never
  converted (mIU/mL ≠ µIU/mL).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any, Iterable, Literal
from app.domain.consistency_config import ANNOTATION_ONLY_CODES, ANNOTATION_FEATURES

Status = Literal["LOW", "NORMAL", "HIGH", "UNKNOWN"]
_UNSIGNED = r"(?:\d{1,3}(?:\.\d{3})+,\d+|\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][+-]?\d+)?"
# "1.234,5" (Turkish thousands + decimal comma) is unambiguous and accepted
# first; "250.000" stays a decimal-looking token until unit context says that it
# is a grouped count (see ``_number``).
_NUMBER = rf"[+-]?{_UNSIGNED}"
_GROUPED_THOUSANDS = re.compile(r"[+-]?\d{1,3}(?:\.\d{3})+")
_TURKISH_FULL = re.compile(r"[+-]?\d{1,3}(?:\.\d{3})+,\d+")
_PLAIN_LARGE_INTEGER = re.compile(r"[+-]?\d{4,}")
_DASHES = "-‐‑‒–—−"
# Source flags printed next to a value ("5.2 H", "7,1*", "180 ↑", "(L)").
_VALUE_FLAG = re.compile(
    r"\s*(?:\(\s*(?:HH|LL|H|L|Y|D|\*+)\s*\)|\*+|[↑↓]+|(?:(?<=\d)|(?<=\s))(?:HH|LL|H|L|Y|D|HIGH|LOW|y[uü]ksek|d[uü][sş][uü]k)\.?)\s*$",
    re.IGNORECASE,
)
_VALUE = re.compile(rf"^(?P<op><=|>=|<|>)?\s*(?P<value>{_NUMBER})(?:\s+(?P<unit>\S.*)|(?P<tight_unit>[^\d\s.,].*))?$")
_RANGE = re.compile(
    rf"^(?P<low>{_NUMBER})\s*(?:[{_DASHES}]|\.\.\.?)\s*(?P<high>{_NUMBER})(?:\s*(?P<unit>\S.*))?$"
)
# "-2 / +2" (base excess style): a slash separates bounds only when the printed
# signs make the interval explicit.
_SIGNED_SLASH_RANGE = re.compile(
    rf"^(?P<low>-\s*{_UNSIGNED})\s*/\s*(?P<high>\+?\s*{_UNSIGNED})(?:\s*(?P<unit>\S.*))?$"
)
_LIMIT = re.compile(rf"^(?P<op><=|>=|<|>)\s*(?P<value>{_NUMBER})(?:\s*(?P<unit>\S.*))?$")
# "40 >" is printed by some systems for "> 40" and by others for "x < 40";
# the direction is not provable, so it is never guessed.
_TRAILING_COMPARATOR = re.compile(rf"^{_NUMBER}\s*(?:<=|>=|<|>)(?:\s*\S.*)?$")
_REFERENCE_LABEL = re.compile(
    r"^(?:ref(?:erence|erans)?\.?(?:\s+(?:range|aral[iı]ğ[iı]|aralik|aral[iı]k|de[gğ]er(?:i|leri)?))?"
    r"|normal(?:\s+(?:range|de[gğ]er(?:i|leri)?))?|n)\s*[:=]\s*",
    re.IGNORECASE,
)
_SEX_LABEL = re.compile(
    r"(?<![A-Za-zÇĞİÖŞÜçğıöşü])(?P<label>erkek(?:ler)?|kad[ıi]n(?:lar)?|male|female|men|women|bay|bayan|[EKMF](?=\s*:))\s*[:=]?\s*",
    re.IGNORECASE,
)
_UNSAFE_REASON = re.compile(
    r"conflict|missing_parameter|missing_observed|invalid_reference|"
    r"reference_unit_mismatch|observed_unit_mismatch|unverified_observed_unit|invalid_numeric|low_input_confidence"
)
_NEGATIVE_WORDS = frozenset({"negatif", "negative", "neg", "(-)", "yok", "saptanmadi", "not detected", "nonreactive", "non-reactive", "reaktif degil"})
_POSITIVE_WORDS = frozenset({"pozitif", "positive", "pos", "(+)", "var", "saptandi", "detected", "reactive", "reaktif"})


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
    status_explanation: str | None = None


@dataclass(frozen=True)
class _Interval:
    low: Decimal | None
    high: Decimal | None
    low_inclusive: bool = True
    high_inclusive: bool = True


def _number(value: Any, *, grouped_thousands: bool = False) -> Decimal | None:
    """Parse one printed number.

    ``grouped_thousands`` is set only from source context (a count-per-volume
    unit, or a row that mixes "250.000" with a plain 4+ digit integer).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    else:
        text = re.sub(r"(?<=[+-])\s+", "", str(value).strip().replace("−", "-"))
    if _TURKISH_FULL.fullmatch(text):
        text = text.replace(".", "").replace(",", ".")
    elif grouped_thousands and _GROUPED_THOUSANDS.fullmatch(text):
        text = text.replace(".", "")
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


_SUPERSCRIPTS = str.maketrans({"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
                               "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9"})
# Spellings of the SAME quantity with a conversion factor of exactly 1. Units
# that differ by a factor (mIU/mL vs µIU/mL, mg/dL vs mmol/L, g/dL vs g/L) are
# never aliased: they stay different and produce reference_unit_mismatch.
_UNIT_ALIASES = {
    "10^3/ul": ("k/ul", "k/mm3", "10^3/mm3", "10^9/l", "bin/ul", "10^3/mcl", "thou/ul", "e3/ul"),
    "10^6/ul": ("m/ul", "m/mm3", "10^6/mm3", "10^12/l", "milyon/ul", "e6/ul"),
    "/ul": ("/mm3", "/mcl", "cells/ul", "cell/ul", "hücre/ul", "hucre/ul", "adet/ul"),
    "miu/l": ("uiu/ml", "uu/ml", "mu/l"),
    "u/l": ("iu/l",),
    "ug/l": ("ng/ml",),
    "ng/l": ("pg/ml",),
    "mm/h": ("mm/saat", "mm/sa", "mm/hr", "mm/1h", "mm/1saat", "mm/1.saat"),
    "ml/min/1.73m2": ("ml/dk/1.73m2", "ml/min/1.73m^2", "ml/dk/1.73m^2", "ml/min/1,73m2", "ml/dk/1,73m2"),
}
_UNIT_ALIAS_LOOKUP = {alias: canonical for canonical, aliases in _UNIT_ALIASES.items()
                      for alias in (canonical, *aliases)}
_COUNT_PER_VOLUME_UNITS = frozenset({"/ul"})


def canonical_lab_unit(value: str | None) -> str | None:
    """Typographic normalisation plus factor-1 spelling aliases (K/µL ≡ 10³/µL).

    This never converts a value between units with different magnitudes.
    """
    unit = normalize_lab_unit(value)
    if unit is None:
        return None
    unit = re.sub(r"10([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: "10^" + m.group(1).translate(_SUPERSCRIPTS), unit)
    unit = unit.translate(_SUPERSCRIPTS)
    unit = unit.replace("mcg", "ug").replace("×", "x").replace("**", "^").replace("10*", "10^")
    unit = re.sub(r"^x(?=10\^)", "", unit)
    return _UNIT_ALIAS_LOOKUP.get(unit, unit)


def is_count_per_volume_unit(value: str | None) -> bool:
    return canonical_lab_unit(value) in _COUNT_PER_VOLUME_UNITS


def _same_unit(left: str | None, right: str | None) -> bool:
    return canonical_lab_unit(left) == canonical_lab_unit(right)


# Physical unit spellings only; this list supplies no medical reference values.
_INLINE_UNITS = frozenset(canonical_lab_unit(value) for value in (
    '%', 'mg/L', 'mg/dL', 'g/L', 'g/dL', 'ng/mL', 'ng/L', 'pg/mL', 'pg',
    'ug/L', 'ug/dL', 'ug/mL', 'mmol/L', 'umol/L', 'mEq/L', 'mol/L',
    'U/L', 'IU/L', 'U/mL', 'IU/mL', 'mIU/L', 'uIU/mL', 'mU/L',
    '10^9/L', '10^12/L', '10^3/uL', '10^6/uL', '10³/uL', '10⁶/uL',
    '10⁹/L', '10¹²/L', '/uL', 'cells/uL', 'fL', 'mm/h', 'mm/saat',
    'mL/min', 'mL/min/1.73m2', 'mL/min/1.73m²', 'mmHg',
    'K/uL', 'M/uL', '/mm3', 'mIU/mL', 'nmol/L', 'pmol/L', 'mU/mL', 'kU/L',
))


@dataclass(frozen=True)
class ParsedObservation:
    number: Decimal | None
    comparator: str | None = None
    inline_unit: str | None = None
    error: str | None = None
    source_flag: str | None = None


def _strip_value_flag(text: str) -> tuple[str, str | None]:
    match = _VALUE_FLAG.search(text)
    if match and match.start() > 0 and re.search(r"\d", text[:match.start()]):
        return text[:match.start()].rstrip(), match.group(0).strip()
    return text, None


def parse_lab_observation(value: Any, unit: str | None = None, *, grouped_thousands: bool | None = None) -> ParsedObservation:
    if isinstance(value, bool) or value is None:
        return ParsedObservation(None, error='invalid_observed_value')
    if isinstance(value, (int, float, Decimal)):
        number = _number(value)
        return ParsedObservation(number) if number is not None else ParsedObservation(None, error='invalid_observed_value')
    text = str(value).strip().replace('≤', '<=').replace('≥', '>=').replace('−', '-')
    text, flag = _strip_value_flag(text)
    match = _VALUE.fullmatch(text)
    if match is None:
        return ParsedObservation(None, error='invalid_observed_value')
    inline = match['unit'] or match['tight_unit']
    if grouped_thousands is None:
        grouped_thousands = is_count_per_volume_unit(unit) or is_count_per_volume_unit(inline)
    number = _number(match['value'], grouped_thousands=grouped_thousands)
    if number is None:
        return ParsedObservation(None, error='invalid_observed_value')
    if inline:
        if canonical_lab_unit(inline) not in _INLINE_UNITS:
            return ParsedObservation(None, error='unverified_observed_unit')
        if normalize_lab_unit(unit) and not _same_unit(unit, inline):
            return ParsedObservation(None, error='observed_unit_mismatch')
    return ParsedObservation(number, match['op'], inline, source_flag=flag)


@dataclass(frozen=True)
class ParsedReference:
    low: Decimal | None
    high: Decimal | None
    low_inclusive: bool = True
    high_inclusive: bool = True
    unit: str | None = None
    error: str | None = None
    selected_text: str | None = None


def _fold(text: str) -> str:
    return text.translate(str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")).casefold()


def _normalize_sex(value: Any) -> str | None:
    folded = _fold(str(value or "")).strip()
    if folded in {"male", "m", "e", "erkek", "man", "bay"}:
        return "male"
    if folded in {"female", "f", "k", "kadin", "woman", "bayan"}:
        return "female"
    return None


def _label_sex(label: str) -> str:
    folded = _fold(label)
    return "female" if folded.startswith(("k", "f", "w", "bayan")) else "male"


def _clean_reference_segment(text: str) -> str:
    text = text.strip().strip(";,|/").strip()
    # Remove one layer of enclosing brackets: "(3.5-5.1)" or "[3.5-5.1]".
    while len(text) >= 2 and text[0] in "([{" and text[-1] in ")]}" and not re.search(r"[)\]}]", text[1:-1]):
        text = text[1:-1].strip()
    text = text.strip().strip(";,|").strip()
    # A dangling "(" left by "> 40 (kadın > 50)" splitting.
    text = re.sub(r"\s*[(\[]\s*$", "", text)
    text = re.sub(r"^\s*[)\]]\s*", "", text)
    if text.endswith((")", "]")) and not re.search(r"[(\[]", text):
        text = text[:-1]
    return text.strip()


def _sex_specific_segments(raw: str) -> dict[str, str] | None:
    """Return {"male": text, "female": text} when the source prints both.

    An unlabeled leading reference followed by one labeled sex ("> 40 (kadın >
    50)") is the reference for the other sex, exactly as printed.
    """
    labels = list(_SEX_LABEL.finditer(raw))
    if not labels:
        return None
    segments: dict[str, str] = {}
    for index, match in enumerate(labels):
        end = labels[index + 1].start() if index + 1 < len(labels) else len(raw)
        sex = _label_sex(match.group('label'))
        if sex in segments:
            return {}  # repeated label: ambiguous
        segments[sex] = _clean_reference_segment(raw[match.end():end])
    prefix = _clean_reference_segment(raw[:labels[0].start()])
    if prefix and re.search(r"\d", prefix):
        if len(segments) != 1:
            return {}
        other = "male" if "female" in segments else "female"
        segments[other] = prefix
    if len(segments) < 2:
        return None  # single labeled row: the caller selected it
    return segments


def has_sex_specific_segments(text: str | None) -> bool:
    """True when one printed reference contains rows for both sexes."""
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    return bool(raw and _sex_specific_segments(raw))


def parse_source_reference(
    text: str | None,
    minimum: Any = None,
    maximum: Any = None,
    *,
    unit: str | None = None,
    patient_sex: str | None = None,
    grouped_thousands: bool | None = None,
) -> ParsedReference:
    raw = str(text or '').strip().replace('≤', '<=').replace('≥', '>=').replace('−', '-')
    raw = re.sub(r"\s+", " ", raw)
    count_context = grouped_thousands if grouped_thousands is not None else is_count_per_volume_unit(unit)
    low, high = _number(minimum, grouped_thousands=count_context), _number(maximum, grouped_thousands=count_context)
    if (minimum is not None and low is None) or (maximum is not None and high is None):
        return ParsedReference(low, high, error='invalid_reference_bounds')

    segments = _sex_specific_segments(raw) if raw else None
    if segments == {}:
        return ParsedReference(low, high, error='invalid_reference_text')
    selected_text = None
    if segments:
        sex = _normalize_sex(patient_sex)
        if sex is None:
            return ParsedReference(None, None, error='sex_specific_reference_requires_patient_sex')
        selected = parse_source_reference(segments[sex], minimum, maximum, unit=unit, grouped_thousands=grouped_thousands)
        return ParsedReference(selected.low, selected.high, selected.low_inclusive, selected.high_inclusive,
                               selected.unit, selected.error, segments[sex])

    # Generic report labels are safe to remove without demographic inference.
    comparable = _clean_reference_segment(_REFERENCE_LABEL.sub('', raw, count=1))
    if comparable == _clean_reference_segment(raw) and ':' in raw and (low is not None or high is not None):
        # The caller selected the structured age/sex row before arriving here.
        comparable = _clean_reference_segment(raw.rsplit(':', 1)[-1])
    interval = _RANGE.fullmatch(comparable) or _SIGNED_SLASH_RANGE.fullmatch(comparable)
    limit = _LIMIT.fullmatch(comparable)
    li = hi = True
    suffix = None
    if interval:
        suffix = interval['unit']
        grouped = count_context or is_count_per_volume_unit(suffix)
        a = _number(interval['low'], grouped_thousands=grouped)
        b = _number(re.sub(r"^\+\s*", "", interval['high']), grouped_thousands=grouped)
        if a is None or b is None:
            return ParsedReference(low, high, error='invalid_reference_bounds')
        if (low is not None and low != a) or (high is not None and high != b):
            return ParsedReference(low, high, error='reference_bounds_conflict')
        low, high = a, b
    elif limit:
        op, suffix = limit['op'], limit['unit']
        number = _number(limit['value'], grouped_thousands=count_context or is_count_per_volume_unit(suffix))
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
    elif _TRAILING_COMPARATOR.fullmatch(comparable):
        return ParsedReference(None, None, error='ambiguous_reference_direction')
    elif raw:
        if low is None and high is None and _fold(comparable) in _NEGATIVE_WORDS | _POSITIVE_WORDS:
            return ParsedReference(None, None, error='qualitative_reference')
        return ParsedReference(low, high, error='invalid_reference_text' if low is not None or high is not None else 'missing_numeric_reference')
    if low is not None and high is not None and low > high:
        return ParsedReference(low, high, error='invalid_reference_bounds')
    if low is None and high is None:
        return ParsedReference(low, high, error='missing_numeric_reference')
    return ParsedReference(low, high, li, hi, suffix, selected_text=selected_text)


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


_REASON_TEXT = {
    'missing_numeric_reference': "Referans aralığı raporda yok",
    'qualitative_reference': "Referans niteliksel; sayısal karşılaştırma yapılmadı",
    'qualitative_differs_from_reference': "Niteliksel sonuç rapordaki referanstan farklı",
    'sex_specific_reference_requires_patient_sex': "Referans cinsiyete göre değişiyor; hasta cinsiyeti bilinmediği için karşılaştırılmadı",
    'ambiguous_reference_direction': "Referansın yönü (< veya >) raporda belirsiz; karşılaştırılmadı",
    'reference_unit_mismatch': "Sonuç birimi ile referans birimi farklı; birim dönüşümü yapılmadı",
    'reference_bounds_conflict': "Referans metni ile okunan sınırlar çelişiyor; hekim kontrolü gerekli",
    'invalid_reference_bounds': "Referans sınırları okunamadı; hekim kontrolü gerekli",
    'invalid_reference_text': "Referans metni yorumlanamadı; hekim kontrolü gerekli",
    'ingestion_review_required': "Okuma doğrulaması gerekiyor; durum atanmadı",
    'invalid_observed_value': "Sonuç değeri sayısal olarak okunamadı",
    'unverified_observed_unit': "Sonuç değerinin yanındaki birim doğrulanamadı",
    'observed_unit_mismatch': "Sonuç içindeki birim ile birim sütunu farklı",
    'ambiguous_censored_value': "Sonuç sınır değeri (<, >) referansa göre kesin konumlandırılamıyor",
}


def describe_lab_status(status: str | None, reason: str | None, raw_reference: str | None = None) -> str | None:
    """Human-readable Turkish explanation for UNKNOWN results (never a raw code)."""
    if status != "UNKNOWN":
        return None
    text = _REASON_TEXT.get(str(reason or ''), "Değerlendirilemedi")
    if reason == 'missing_numeric_reference' and raw_reference and str(raw_reference).strip():
        return f"Raporda sayısal referans aralığı yok (referans: {str(raw_reference).strip()})"
    if reason == 'qualitative_differs_from_reference' and raw_reference:
        return f"{text} (referans: {str(raw_reference).strip()})"
    return text


def humanize_status_codes(text: str) -> str:
    """Replace raw status/reason codes that leaked into narrative text.

    The AI report must say e.g. "Referans aralığı raporda yok", never "UNKNOWN".
    """
    if not text:
        return text
    for code, label in _REASON_TEXT.items():
        text = re.sub(rf"\b{re.escape(code)}\b", label, text)
    text = re.sub(r"\(\s*UNKNOWN\s*\)", "(değerlendirilemedi)", text)
    return re.sub(r"\bUNKNOWN\b", "değerlendirilemedi", text)


def _qualitative_class(value: Any) -> str | None:
    folded = _fold(str(value or "")).strip().strip(".")
    folded = re.sub(r"\s+", " ", folded)
    if folded in _NEGATIVE_WORDS:
        return "negative"
    if folded in _POSITIVE_WORDS:
        return "positive"
    return None


def _mixed_grouping(*tokens: Any) -> bool:
    texts = [str(item).strip() for item in tokens if isinstance(item, str) and str(item).strip()]
    grouped = any(_GROUPED_THOUSANDS.search(text) for text in texts)
    plain = any(_PLAIN_LARGE_INTEGER.fullmatch(re.sub(r"^[<>=]+\s*", "", text)) for text in texts)
    return grouped and plain


def classify_lab_result(
    *,
    value: Any,
    unit: str | None = None,
    reference_text: str | None = None,
    reference_low: Any = None,
    reference_high: Any = None,
    reference_unit: str | None = None,
    ingestion_reasons: Iterable[Any] | None = (),
    patient_sex: str | None = None,
) -> LabClassification:
    """Return source-preserving status; numeric structured references are optional.

The caller must first select any age/sex-specific source reference. Structured
bounds can represent that selected row even when its text includes a demographic
label. If plain numeric reference text is present, its bounds must agree with the
structured bounds. No source flag or incoming status can override comparison.
A reference that prints both sexes is resolved only with ``patient_sex``.
"""
    raw_reference = reference_text
    grouped = (
        is_count_per_volume_unit(unit) or is_count_per_volume_unit(reference_unit)
        or _mixed_grouping(value, *(reference_text.replace('-', ' ').split() if isinstance(reference_text, str) else ()))
    )
    reference = parse_source_reference(reference_text, reference_low, reference_high,
                                       unit=unit, patient_sex=patient_sex, grouped_thousands=grouped)
    low, high = reference.low, reference.high
    lower_inclusive, upper_inclusive = reference.low_inclusive, reference.high_inclusive
    text_unit = reference.unit
    observation = parse_lab_observation(value, unit, grouped_thousands=grouped or None)

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
            status_explanation=describe_lab_status(status, reason, raw_reference),
        )

    if reference.error == 'qualitative_reference':
        expected, observed_class = _qualitative_class(reference_text and _clean_reference_segment(
            _REFERENCE_LABEL.sub('', str(reference_text).strip(), count=1))), _qualitative_class(value)
        if observed_class is None:
            return result('UNKNOWN', 'qualitative_reference')
        if not _ingestion_is_safe(ingestion_reasons):
            return result("UNKNOWN", "ingestion_review_required")
        if observed_class == expected:
            return result('NORMAL', 'matches_qualitative_source_reference')
        return result('UNKNOWN', 'qualitative_differs_from_reference')

    if reference.error:
        return result('UNKNOWN', reference.error)

    measured_unit = canonical_lab_unit(unit) or canonical_lab_unit(observation.inline_unit)
    supplied_units = {canonical_lab_unit(item) for item in (reference_unit, text_unit) if canonical_lab_unit(item)}
    if supplied_units and (len(supplied_units) != 1 or measured_unit not in supplied_units):
        return result("UNKNOWN", "reference_unit_mismatch")

    if not _ingestion_is_safe(ingestion_reasons):
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
    if (
        comparator in ("<", "<=") and low == 0 and lower_inclusive
        and _subset(_Interval(low, number, True, comparator == "<="), normal)
    ):
        # A reference printed from 0 states the assay's lower limit, so "<0,5"
        # against "0-5" lies inside the printed interval.
        return result("NORMAL", "within_zero_based_source_reference")
    return result("UNKNOWN", "ambiguous_censored_value")


def _ingestion_is_safe(ingestion_reasons: Iterable[Any] | None) -> bool:
    reasons = (ingestion_reasons,) if isinstance(ingestion_reasons, str) else (ingestion_reasons or ())
    from app.core.config import get_settings
    annotation_active = any(getattr(get_settings(), name, False) for name in ANNOTATION_FEATURES)
    return not any(
        not (annotation_active and str(reason) in ANNOTATION_ONLY_CODES) and _UNSAFE_REASON.search(str(reason))
        for reason in reasons
    )
