"""Pure-Python deterministic laboratory processing for MediCore.

The module intentionally keeps the deterministic layer small: it validates numeric
values, preserves source reference ranges, classifies values against those ranges,
and fails closed to physician review when evidence is incomplete.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

LAB_PYTHON_CONTRACT = "medicore-python-lab-v1"
LAB_VALIDATION_CONTRACT = "medicore-python-lab-validation-v1"
LAB_METRICS_CONTRACT = "medicore-python-lab-metrics-v1"
PYTHON_PROVENANCE_CONTRACT = "medicore-lab-provenance-python-v1"

_MIN_TRUST_CONFIDENCE = 0.85


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _identity(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    name = str(
        row.get("canonical_name")
        or row.get("display_name")
        or row.get("raw_parameter_name")
        or ""
    ).strip().casefold()
    return (
        name,
        str(row.get("measured_at") or ""),
        str(row.get("normalized_value") or row.get("raw_value") or ""),
        str(row.get("unit") or ""),
        str(row.get("source_record_id") or row.get("source_file_name") or ""),
    )


def _classify_row(source: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(source)
    value = _decimal(row.get("normalized_value"))
    low = _decimal(row.get("reference_min") or row.get("extracted_reference_min"))
    high = _decimal(row.get("reference_max") or row.get("extracted_reference_max"))

    confidence_raw = row.get("confidence")
    if confidence_raw is None:
        confidence_raw = row.get("extraction_confidence")
    try:
        extraction_confidence = float(confidence_raw) if confidence_raw is not None else 1.0
    except (TypeError, ValueError):
        extraction_confidence = 0.0

    explicit_review = bool(row.get("needs_review"))
    display_name = str(
        row.get("display_name")
        or row.get("canonical_name")
        or row.get("raw_parameter_name")
        or "Bilinmeyen test"
    ).strip()

    validation_status = "VALID"
    needs_review = explicit_review
    result_status = "NEEDS_REVIEW"
    rule_applied = "python_missing_reference"
    reason = "Kaynak raporda güvenilir referans sınırı bulunamadı."
    classification_confidence = 0.0

    if value is None:
        validation_status = "NEEDS_REVIEW"
        needs_review = True
        rule_applied = "python_missing_numeric"
        reason = "Sayısal sonuç güvenilir biçimde çıkarılamadı."
    elif low is not None and high is not None and low > high:
        validation_status = "INVALID"
        needs_review = True
        rule_applied = "python_invalid_reference"
        reason = "Kaynak rapordaki referans aralığı geçersiz."
    elif extraction_confidence < _MIN_TRUST_CONFIDENCE:
        validation_status = "NEEDS_REVIEW"
        needs_review = True
        rule_applied = "python_low_extraction_confidence"
        reason = "Belge çıkarım güveni hekim onayı gerektiriyor."
    elif explicit_review:
        validation_status = "NEEDS_REVIEW"
        needs_review = True
        rule_applied = "python_source_review_required"
        reason = str(row.get("reason") or row.get("extraction_note") or "Kaynak satır hekim kontrolü gerektiriyor.")
    elif low is not None and value < low:
        result_status = "LOW"
        rule_applied = "python_below_source_min"
        reason = "Değer kaynak rapordaki referans alt sınırının altında."
        classification_confidence = extraction_confidence
    elif high is not None and value > high:
        result_status = "HIGH"
        rule_applied = "python_above_source_max"
        reason = "Değer kaynak rapordaki referans üst sınırının üzerinde."
        classification_confidence = extraction_confidence
    elif low is not None or high is not None:
        result_status = "NORMAL"
        rule_applied = "python_within_source_reference"
        reason = "Değer kaynak rapordaki mevcut referans sınırları içinde."
        classification_confidence = extraction_confidence
    else:
        validation_status = "NEEDS_REVIEW"
        needs_review = True

    return {
        **row,
        "display_name": display_name,
        "normalized_value": value,
        "reference_min": low,
        "reference_max": high,
        "extraction_confidence": extraction_confidence,
        "result_status": result_status,
        "validation_status": validation_status,
        "needs_review": needs_review,
        "reason": reason,
        "rule_applied": rule_applied,
        "classification_confidence": classification_confidence,
        "contract_version": LAB_PYTHON_CONTRACT,
        "validation_contract_version": LAB_VALIDATION_CONTRACT,
        "provenance_contract_version": PYTHON_PROVENANCE_CONTRACT,
    }


def process_lab_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate/classify rows and remove exact duplicate observations."""
    processed: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for source in rows:
        if not isinstance(source, Mapping):
            continue
        key = _identity(source)
        if key in seen:
            continue
        seen.add(key)
        processed.append(_classify_row(source))

    return processed


def compute_python_lab_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    patient_age: int | None = None,
    patient_sex: str | None = None,
) -> list[dict[str, Any]]:
    """Return no speculative derived metrics in the simplified MVP.

    Derived scores can be reintroduced one-by-one after their input requirements,
    formulas and validation tests are explicitly specified.
    """
    del rows, patient_age, patient_sex
    return []
