"""Runtime corrections for full PDF blood-row extraction.

The PDF upload path must not depend on dynamically inserting every previously
unknown test into ``clinical_parameters``. Any numeric blood-test row that has a
reference interval printed in the PDF can be classified deterministically from
that source range even when MediCore does not yet know the parameter name.

This runtime layer also keeps CBC absolute (#) and percentage (%) names distinct,
filters footer phone numbers, preserves rows without a printed reference for
human review, canonicalizes common report naming variants before mapping, and
filters non-test note rows.
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


# Common report spellings that otherwise become dynamic PDF parameters. Score /
# index rows (TyG, LDL/HDL ratio, FIB-4, estimated average glucose) intentionally
# remain outside automatic range guessing unless a trusted parameter/range exists.
_KNOWN_DISPLAY_NAME_BY_KEY: dict[str, str] = {
    # Lipids / liver
    "CHOLESTEROL": "Total Kolesterol",
    "CHOLESTROL": "Total Kolesterol",
    "TOTALCHOLESTEROL": "Total Kolesterol",
    "TOTALCHOLESTROL": "Total Kolesterol",
    "TOTALKOLESTEROL": "Total Kolesterol",
    "NONHDL": "Non-HDL",
    "NONHDLCHOLESTEROL": "Non-HDL",
    "NONHDLCHOLESTROL": "Non-HDL",
    "NONHDLKOLESTEROL": "Non-HDL",
    "TRIGLYCERIDE": "TRIGLISERIT",
    "TRIGLYCERIDES": "TRIGLISERIT",
    "TRIGLISERIT": "TRIGLISERIT",
    "TRIGLISERID": "TRIGLISERIT",
    "HDL": "HDL",
    "HDLCHOLESTEROL": "HDL",
    "HDLCHOLESTROL": "HDL",
    "HDLKOLESTEROL": "HDL",
    "LDL": "LDL",
    "LDLCHOLESTEROL": "LDL",
    "LDLCHOLESTROL": "LDL",
    "LDLKOLESTEROL": "LDL",
    "SGOT": "AST",
    "SGOTAST": "AST",
    "AST": "AST",
    "ASPARTATEAMINOTRANSFERASE": "AST",
    "ASPARTATAMINOTRANSFERAZ": "AST",

    # CBC differential percentages. The Render catalog already contains these
    # canonical parameters with age/sex-aware reference ranges.
    "NEUTROPHIL": "Nötrofil %",
    "NEUTROPHILS": "Nötrofil %",
    "NEUTROPHILPCT": "Nötrofil %",
    "LYMPHOCYTE": "Lenfosit %",
    "LYMPHOCYTES": "Lenfosit %",
    "LYMPHOCYTEPCT": "Lenfosit %",
    "MONOCYTE": "Monosit %",
    "MONOCYTES": "Monosit %",
    "MONOCYTEPCT": "Monosit %",
    "EOSINOPHIL": "Eozinofil %",
    "EOSINOPHILS": "Eozinofil %",
    "EOSINOPHILPCT": "Eozinofil %",
    "BASOPHIL": "Bazofil %",
    "BASOPHILS": "Bazofil %",
    "BASOPHILPCT": "Bazofil %",

    # Common English / abbreviated glucose and inflammation names.
    "FBS": "Glukoz",
    "FASTINGBLOODSUGAR": "Glukoz",
    "FASTINGGLUCOSE": "Glukoz",
    "HBA1C": "HbA1c",
    "ESR": "Sedimentasyon",
    "ERYTHROCYTESEDIMENTATIONRATE": "Sedimentasyon",
}

# Some reports render an upper decision limit as e.g.
# "Triglycerides 127 mg/dL - - 200 mg/dL". That shape is not a true two-sided
# reference interval, so only use it to recover the row. The existing MediCore
# deterministic lipid policy supplies the actual classification range later.
_DASH_LIMIT_ROW_RE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<value>[<>]?\s*[-+]?\d+(?:\.\d+)?)\s+"
    r"(?P<unit>---|[%A-Za-z0-9^./]+(?:/[A-Za-z0-9.^]+)*)\s+"
    r"(?:-\s*){1,2}(?P<limit>[-+]?\d+(?:\.\d+)?)"
    r"(?:\s+[%A-Za-z0-9^./]+(?:/[A-Za-z0-9.^]+)*)?\s*$",
    flags=re.IGNORECASE,
)

_original_numeric_row = lab_pdf_system_extract._row_from_numeric_match
_original_process_value = AnalysisPipeline._process_value
_original_parse_all_blood_rows = lab_pdf_system_extract._parse_all_blood_rows
_original_map_rows_to_parameters = lab_pdf_system_extract._map_rows_to_parameters


def _canonicalize_known_row(row: dict[str, Any]) -> dict[str, Any]:
    display_name = str(row.get("display_name") or "").strip()
    canonical = _KNOWN_DISPLAY_NAME_BY_KEY.get(_name_key(display_name))
    if canonical is None:
        return row

    row["display_name"] = canonical

    # HbA1c is sometimes exported with a lone upper decision value (e.g. "-- 6.5").
    # A single bound is insufficient for the existing RuleEngine; once the name is
    # mapped with high confidence, let ReferenceResolver use the catalog's trusted
    # age/sex-aware interval instead of treating the partial PDF bound as uncertain.
    if canonical == "HbA1c":
        low = row.get("extracted_reference_min")
        high = row.get("extracted_reference_max")
        if (low is None) != (high is None):
            row["extracted_reference_min"] = None
            row["extracted_reference_max"] = None

    # Reuse the already-established deterministic demo references for common
    # lipid markers. Do not invent ranges for calculated scores/indexes.
    if row.get("extracted_reference_min") is None or row.get("extracted_reference_max") is None:
        forced_reference = lab_analysis._forced_demo_reference(canonical)
        if forced_reference is not None:
            unit, low, high = forced_reference
            row["unit"] = unit
            row["extracted_unit"] = unit
            row["extracted_reference_min"] = low
            row["extracted_reference_max"] = high

    return row


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
    return _canonicalize_known_row(row)


def _is_note_pseudo_test(row: dict[str, Any]) -> bool:
    key = _name_key(str(row.get("display_name") or ""))
    return key in {"NOTE", "NOT", "COMMENT", "COMMENTS", "ACIKLAMA"}


def _parse_all_blood_rows(text: str, report_date: date) -> list[dict[str, Any]]:
    rows = [
        _canonicalize_known_row(row)
        for row in _original_parse_all_blood_rows(text, report_date)
        if not _is_note_pseudo_test(row)
    ]
    seen = {_name_key(str(row.get("display_name") or "")) for row in rows}

    # Recover known lipid rows with the odd "- - limit" export shape.
    for raw_line in text.splitlines():
        line = lab_pdf_system_extract._clean_line(raw_line)
        match = _DASH_LIMIT_ROW_RE.match(line)
        if match is None:
            continue

        raw_name = str(match.group("name") or "").strip(" :-")
        canonical = _KNOWN_DISPLAY_NAME_BY_KEY.get(_name_key(raw_name))
        if canonical not in {"Total Kolesterol", "Non-HDL", "TRIGLISERIT", "HDL", "LDL"}:
            continue

        key = _name_key(canonical)
        if key in seen:
            continue

        value = lab_pdf_system_extract._parse_number(str(match.group("value") or ""))
        if value is None:
            continue

        unit = str(match.group("unit") or "").strip()
        if unit == "---":
            unit = ""

        row = _canonicalize_known_row(
            {
                "display_name": canonical,
                "raw_value": str(match.group("value") or "").strip(),
                "normalized_value": value,
                "unit": unit,
                "extracted_reference_min": None,
                "extracted_reference_max": None,
                "extracted_unit": unit,
                "measured_at": report_date.isoformat(),
                "qualitative_normal": False,
            }
        )
        rows.append(row)
        seen.add(key)

    return rows


def _map_rows_to_parameters(
    rows: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    canonical_rows = [
        _canonicalize_known_row(row)
        for row in rows
        if not _is_note_pseudo_test(row)
    ]
    return _original_map_rows_to_parameters(canonical_rows, catalog)


async def _ensure_dynamic_parameters(rows: list[dict[str, Any]]) -> None:
    """Deliberately do nothing.

    Unknown PDF tests do not need a permanent clinical-parameter row merely to
    classify a value against the reference interval printed in the report.
    """
    return None


def _to_pipeline_values(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        if _is_note_pseudo_test(row):
            continue

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
lab_pdf_system_extract._parse_all_blood_rows = _parse_all_blood_rows
lab_pdf_system_extract._map_rows_to_parameters = _map_rows_to_parameters
lab_pdf_system_extract._ensure_dynamic_parameters = _ensure_dynamic_parameters
lab_pdf_system_extract._to_pipeline_values = _to_pipeline_values
AnalysisPipeline._process_value = _process_value_with_pdf_reference_fallback
