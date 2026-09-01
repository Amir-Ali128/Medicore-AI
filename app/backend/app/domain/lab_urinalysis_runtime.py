"""Extend the PDF-first lab parser with urinalysis rows.

Blood-test counting remains available in the report metadata, but clinically relevant
urinalysis rows are also persisted so semiquantitative findings such as glucose ++++
can participate in the case summary and deterministic cross-panel checks.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.api.routes import lab_pdf_system_extract as parser_module


_original_parse_all_blood_rows = parser_module._parse_all_blood_rows

_SEMI_VALUES = {
    "negatif": 0.0,
    "negative": 0.0,
    "normal": 0.0,
    "eser": 0.5,
    "trace": 0.5,
    "+": 1.0,
    "++": 2.0,
    "+++": 3.0,
    "++++": 4.0,
    "pozitif": 1.0,
    "positive": 1.0,
}

_URINE_START_MARKERS = (
    "TAM IDRAR ANALIZI",
    "TAM İDRAR ANALİZİ",
    "URINALYSIS",
    "IDRAR TAHLILI",
    "İDRAR TAHLİLİ",
)

_URINE_END_MARKERS = (
    "GAITA",
    "PARAZIT",
    "PARAZİT",
    "ROTAVIRUS",
    "KULTUR",
    "KÜLTÜR",
    "ANTI ",
    "VITAMIN",
    "VİTAMİN",
    "HORMON",
)

_SEMI_RE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<value>Negatif|Negative|Normal|Pozitif|Positive|Eser|Trace|\+{1,4})"
    r"(?:\s+(?P<unit>---|[%A-Za-z0-9^./]+(?:/[A-Za-z0-9.^]+)*))?"
    r"(?:\s+(?P<reference>Negatif|Negative|Normal|Pozitif|Positive|Eser|Trace|\+{1,4}))?$",
    flags=re.IGNORECASE,
)


def _urine_name(value: str) -> str:
    clean = value.strip(" :-")
    if parser_module._name_key(clean).startswith(parser_module._name_key("İdrar")):
        return clean
    return f"İdrar {clean}"


def _semi_row(match: re.Match[str], report_date: date) -> dict[str, Any] | None:
    raw_name = match.group("name").strip(" :-")
    raw_value = match.group("value").strip()
    folded_value = raw_value.lower()
    normalized = _SEMI_VALUES.get(folded_value)
    if normalized is None:
        normalized = _SEMI_VALUES.get(raw_value)
    if normalized is None:
        return None

    raw_reference = (match.groupdict().get("reference") or "Negatif").strip()
    folded_reference = raw_reference.lower()
    reference_value = _SEMI_VALUES.get(folded_reference)
    if reference_value is None:
        reference_value = _SEMI_VALUES.get(raw_reference)

    # If the report's expected value is negative/normal, positive grades become
    # deterministic HIGH findings. Unknown qualitative references remain reviewable.
    low = reference_value if reference_value is not None else None
    high = reference_value if reference_value is not None else None
    unit = (match.groupdict().get("unit") or "").strip()
    if unit == "---":
        unit = ""

    return {
        "display_name": _urine_name(raw_name),
        "raw_value": raw_value,
        "normalized_value": normalized,
        "unit": unit,
        "extracted_reference_min": low,
        "extracted_reference_max": high,
        "extracted_unit": unit,
        "measured_at": report_date.isoformat(),
        "qualitative_normal": normalized == 0.0 and reference_value == 0.0,
        "panel": "urinalysis",
        "semiquantitative": True,
    }


def _parse_urinalysis_rows(text: str, report_date: date) -> list[dict[str, Any]]:
    lines = [parser_module._clean_line(line) for line in text.splitlines()]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    in_urine = False

    for line in lines:
        if not line:
            continue
        upper = line.upper()

        if any(marker in upper for marker in _URINE_START_MARKERS):
            in_urine = True
            continue
        if not in_urine:
            continue
        if line.startswith("Sayfa "):
            in_urine = False
            continue
        if any(marker in upper for marker in _URINE_END_MARKERS) and not upper.startswith("IDRAR"):
            in_urine = False
            continue

        numeric = parser_module._NUMERIC_ROW_RE.match(line)
        if numeric:
            row = parser_module._row_from_numeric_match(numeric, report_date)
            if row:
                row["display_name"] = _urine_name(str(row["display_name"]))
                row["panel"] = "urinalysis"
                row["semiquantitative"] = False
                key = parser_module._name_key(str(row["display_name"]))
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        no_reference = parser_module._NUMERIC_NO_REFERENCE_RE.match(line)
        if no_reference:
            row = parser_module._row_from_numeric_match(no_reference, report_date)
            if row:
                row["display_name"] = _urine_name(str(row["display_name"]))
                row["panel"] = "urinalysis"
                row["semiquantitative"] = False
                key = parser_module._name_key(str(row["display_name"]))
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        semi = _SEMI_RE.match(line)
        if semi:
            row = _semi_row(semi, report_date)
            if row:
                key = parser_module._name_key(str(row["display_name"]))
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)

    return rows


def _parse_all_lab_rows(text: str, report_date: date) -> list[dict[str, Any]]:
    blood_rows = list(_original_parse_all_blood_rows(text, report_date))
    for row in blood_rows:
        row.setdefault("panel", "blood")
        row.setdefault("semiquantitative", False)

    urine_rows = _parse_urinalysis_rows(text, report_date)
    seen = {parser_module._name_key(str(row.get("display_name") or "")) for row in blood_rows}
    combined = list(blood_rows)
    for row in urine_rows:
        key = parser_module._name_key(str(row.get("display_name") or ""))
        if key and key not in seen:
            seen.add(key)
            combined.append(row)
    return combined


# The legacy function name is preserved for callers, but the returned collection now
# includes a separate, clearly prefixed urinalysis panel as well.
parser_module._parse_all_blood_rows = _parse_all_lab_rows
