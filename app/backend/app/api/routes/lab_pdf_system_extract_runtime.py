"""Runtime corrections for full PDF blood-row extraction.

The PDF upload path must not depend on dynamically inserting every previously
unknown test into ``clinical_parameters``. Any numeric blood-test row that has a
reference interval printed in the PDF can be classified deterministically from
that source range even when MediCore does not yet know the parameter name.

This runtime layer also keeps CBC absolute (#) and percentage (%) names distinct,
filters footer phone numbers, and preserves rows without a printed reference for
human review instead of crashing the upload.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.api.routes import lab_analysis, lab_pdf_system_extract
from app.domain.analysis_pipeline import AnalysisPipeline
from app.domain.enums import ResultStatus


def _name_key(value: str) -> str:
    normalized = lab_analysis._normalize_text(value).upper()
    normalized = normalized.replace("#", " ABS ").replace("%", " PCT ")
    return re.sub(r"[^A-Z0-9]+", "", normalized)


_original_numeric_row = lab_pdf_system_extract._row_from_numeric_match
_original_process_value = AnalysisPipeline._process_value


def _row_from_numeric_match(
    match: re.Match[str],
    report_date: date,
) -> dict[str, Any] | None:
    groups = match.groupdict()

    # _NUMERIC_NO_REFERENCE_RE intentionally has no ``unit`` or ``reference``
    # group. Preserve such rows so a known MediCore parameter can still fall
    # back to a stored reference; otherwise the row remains reviewable.
    if "unit" not in groups:
        raw_name = str(groups.get("name") or "").strip(" :-")
        if not raw_name or lab_pdf_system_extract._is_non_blood_test(raw_name):
            return None
        value = lab_pdf_system_extract._parse_number(str(groups.get("value") or ""))
        if value is None:
            return None
        row: dict[str, Any] = {
            "display_name": raw_name,
            "raw_value": str(groups.get("value") or "").strip(),
            "normalized_value": value,
            "unit": "",
            "extracted_reference_min": None,
            "extracted_reference_max": None,
            "extracted_unit": "",
            "measured_at": report_date.isoformat(),
            "qualitative_normal": False,
        }
    else:
        row = _original_numeric_row(match, report_date)
        if row is None:
            return None

    name = str(row.get("display_name") or "").strip()
    if name.startswith("0 850") or name.lower().startswith("sayfa"):
        return None
    return row


async def _ensure_dynamic_parameters(rows: list[dict[str, Any]]) -> None:
    """Deliberately do nothing.

    Unknown PDF tests do not need a permanent clinical-parameter row merely to
    classify a value against the reference interval printed in the report.
    """
    return None


def _to_pipeline_values(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        # Known catalog parameters still use their stable code. Unknown rows use
        # the report's display name so the result remains understandable and the
        # pipeline's extracted-reference fallback can classify it directly.
        raw_name = (
            str(row.get("parameter_code") or "")
            if row.get("dynamic") is not True
            else str(row.get("display_name") or "")
        )
        values.append(
            {
                "raw_parameter_name": raw_name,
                "raw_value": row.get("raw_value"),
                "normalized_value": row.get("normalized_value"),
                "unit": row.get("unit") or None,
                "extracted_reference_min": row.get("extracted_reference_min"),
                "extracted_reference_max": row.get("extracted_reference_max"),
                "extracted_unit": row.get("unit") or None,
                "measured_at": row.get("measured_at"),
            }
        )
    return values


async def _process_value_with_pdf_reference_fallback(
    self: AnalysisPipeline,
    raw: Any,
    *,
    report: Any,
    run: Any,
    patient: Any,
) -> Any:
    result = await _original_process_value(
        self,
        raw,
        report=report,
        run=run,
        patient=patient,
    )

    # Only intervene when the normal alias path could not map the parameter.
    # Known parameters continue through the existing ReferenceResolver/RuleEngine.
    if result.result_status != ResultStatus.UNKNOWN:
        return result
    if raw.normalized_value is None:
        return result

    low = raw.extracted_reference_min
    high = raw.extracted_reference_max
    if low is None or high is None:
        return result

    value = raw.normalized_value
    if value < low:
        status = ResultStatus.LOW
        rule = "pdf_unmapped_value_below_min"
        reason = f"Değer {value}, PDF referans alt sınırı {low} değerinin altındadır."
    elif value > high:
        status = ResultStatus.HIGH
        rule = "pdf_unmapped_value_above_max"
        reason = f"Değer {value}, PDF referans üst sınırı {high} değerinin üzerindedir."
    else:
        status = ResultStatus.NORMAL
        rule = "pdf_unmapped_value_within_range"
        reason = f"Değer {value}, PDF referans aralığı [{low}, {high}] içindedir."

    # Mutate the passive result before it is persisted by AnalysisPipeline.
    result.canonical_name = raw.raw_parameter_name
    result.reference_min = low
    result.reference_max = high
    result.reference_source = "extracted_report"
    result.unit = raw.unit or raw.extracted_unit
    result.result_status = status
    result.needs_review = False
    result.reason = reason
    result.rule_applied = rule
    result.reference_confidence = 0.98
    result.classification_confidence = 1.0
    metadata = dict(result.metadata_json or {})
    metadata.update(
        {
            "pdf_unmapped_reference_classification": True,
            "reference_strategy": "extracted_report",
        }
    )
    result.metadata_json = metadata
    return result


lab_pdf_system_extract._name_key = _name_key
lab_pdf_system_extract._row_from_numeric_match = _row_from_numeric_match
lab_pdf_system_extract._ensure_dynamic_parameters = _ensure_dynamic_parameters
lab_pdf_system_extract._to_pipeline_values = _to_pipeline_values
AnalysisPipeline._process_value = _process_value_with_pdf_reference_fallback
