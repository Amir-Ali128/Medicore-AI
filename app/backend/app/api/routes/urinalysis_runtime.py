"""Parse urinalysis rows that the blood-focused PDF importer intentionally skipped.

Numeric and semiquantitative urine observations are preserved as separate canonical
names prefixed with ``İdrar ·``. Semiquantitative results keep the original raw value
(``+``/``++++``/``Negatif``) while using an ordinal numeric representation only so the
existing deterministic reference engine can classify clearly abnormal report rows.

No diagnosis is inferred from urine values in this layer.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.api.routes import lab_pdf_system_extract


_original_parse_rows = lab_pdf_system_extract._parse_all_blood_rows

_URINE_SECTION_MARKERS = ("TAM IDRAR ANALIZI", "TAM İDRAR ANALİZİ", "URINALYSIS")
_URINE_END_MARKERS = (
    "TAM KAN SAYIMI",
    "HEMOGRAM",
    "BIYOKIMYA",
    "BİYOKİMYA",
    "HORMON",
    "IMMUNOLOJI",
    "İMMÜNOLOJİ",
)

_URINE_SEMI_RE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<value>\+{1,4}|NEGATIF|NEGATİF|NEGATIVE|POZITIF|POZİTİF|POSITIVE|"
    r"NORMAL|ESER|TRACE)"
    r"(?:\s+(?P<unit>---|[%A-Za-z0-9^./]+))?"
    r"(?:\s+(?P<reference>NEGATIF|NEGATİF|NEGATIVE|NORMAL))?$",
    flags=re.IGNORECASE,
)

_EXPECTED_NEGATIVE = (
    "glukoz",
    "glucose",
    "protein",
    "keton",
    "ketone",
    "nitrit",
    "nitrite",
    "bilirubin",
    "kan",
    "blood",
    "hemoglobin",
    "lokosit esteraz",
    "lökosit esteraz",
    "leukocyte esterase",
)


def _fold(value: str) -> str:
    return (
        value.replace("İ", "I")
        .replace("ı", "i")
        .replace("Ş", "S")
        .replace("ş", "s")
        .replace("Ğ", "G")
        .replace("ğ", "g")
        .replace("Ü", "U")
        .replace("ü", "u")
        .replace("Ö", "O")
        .replace("ö", "o")
        .replace("Ç", "C")
        .replace("ç", "c")
        .lower()
    )


def _semi_value(raw: str) -> float:
    value = _fold(raw).strip()
    plus_count = value.count("+")
    if plus_count:
        return float(plus_count)
    if value in {"negatif", "negative", "normal"}:
        return 0.0
    if value in {"eser", "trace"}:
        return 0.5
    if value in {"pozitif", "positive"}:
        return 1.0
    return 0.0


def _prefix(row: dict[str, Any]) -> dict[str, Any]:
    display = str(row.get("display_name") or "").strip()
    return {
        **row,
        "display_name": f"İdrar · {display}",
        "urinalysis": True,
    }


def _semi_row(match: re.Match[str], report_date: date) -> dict[str, Any] | None:
    name = match.group("name").strip(" :-")
    if not name:
        return None
    raw_value = match.group("value").strip()
    unit = (match.groupdict().get("unit") or "").strip()
    if unit == "---":
        unit = ""

    folded_name = _fold(name)
    reference = _fold(match.groupdict().get("reference") or "")
    expected_negative = any(alias in folded_name for alias in _EXPECTED_NEGATIVE)
    has_negative_reference = reference in {"negatif", "negative", "normal"}

    low = 0.0 if expected_negative or has_negative_reference else None
    high = 0.0 if expected_negative or has_negative_reference else None

    return _prefix(
        {
            "display_name": name,
            "raw_value": raw_value,
            "normalized_value": _semi_value(raw_value),
            "unit": unit,
            "extracted_reference_min": low,
            "extracted_reference_max": high,
            "extracted_unit": unit,
            "measured_at": report_date.isoformat(),
            "qualitative_normal": _semi_value(raw_value) == 0,
            "semiquantitative": True,
        }
    )


def _parse_urine_rows(text: str, report_date: date) -> list[dict[str, Any]]:
    lines = [lab_pdf_system_extract._clean_line(line) for line in text.splitlines()]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    in_section = False
    pending_name_parts: list[str] = []

    for line in lines:
        if not line:
            continue
        upper = line.upper()

        if any(marker in upper for marker in _URINE_SECTION_MARKERS):
            in_section = True
            pending_name_parts.clear()
            continue

        if not in_section:
            continue

        if line.startswith("Sayfa "):
            # e-Nabız pages frequently repeat the urinalysis header on the next page;
            # do not treat the footer itself as a row.
            pending_name_parts.clear()
            continue

        if any(marker in upper for marker in _URINE_END_MARKERS):
            in_section = False
            pending_name_parts.clear()
            continue

        numeric = lab_pdf_system_extract._NUMERIC_ROW_RE.match(line)
        if numeric:
            row = lab_pdf_system_extract._row_from_numeric_match(numeric, report_date)
            pending_name_parts.clear()
            if row:
                row = _prefix(row)
                key = lab_pdf_system_extract._name_key(str(row["display_name"]))
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        no_reference = lab_pdf_system_extract._NUMERIC_NO_REFERENCE_RE.match(line)
        if no_reference:
            row = lab_pdf_system_extract._row_from_numeric_match(no_reference, report_date)
            pending_name_parts.clear()
            if row:
                row = _prefix(row)
                key = lab_pdf_system_extract._name_key(str(row["display_name"]))
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        semiquant = _URINE_SEMI_RE.match(line)
        if semiquant:
            row = _semi_row(semiquant, report_date)
            pending_name_parts.clear()
            if row:
                key = lab_pdf_system_extract._name_key(str(row["display_name"]))
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        if re.match(r"^[<>]?\s*[-+]?\d+(?:\.\d+)?\s+", line) and pending_name_parts:
            combined = " ".join([*pending_name_parts[-2:], line])
            numeric = lab_pdf_system_extract._NUMERIC_ROW_RE.match(combined)
            pending_name_parts.clear()
            if numeric:
                row = lab_pdf_system_extract._row_from_numeric_match(numeric, report_date)
                if row:
                    row = _prefix(row)
                    key = lab_pdf_system_extract._name_key(str(row["display_name"]))
                    if key and key not in seen:
                        seen.add(key)
                        rows.append(row)
            continue

        if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", line) and not re.search(r"\d", line):
            pending_name_parts.append(line)
            pending_name_parts[:] = pending_name_parts[-2:]
        else:
            pending_name_parts.clear()

    return rows


def _parse_rows_with_urinalysis(text: str, report_date: date) -> list[dict[str, Any]]:
    blood_rows = list(_original_parse_rows(text, report_date))
    urine_rows = _parse_urine_rows(text, report_date)

    seen = {
        lab_pdf_system_extract._name_key(str(row.get("display_name") or ""))
        for row in blood_rows
    }
    for row in urine_rows:
        key = lab_pdf_system_extract._name_key(str(row.get("display_name") or ""))
        if key and key not in seen:
            seen.add(key)
            blood_rows.append(row)
    return blood_rows


lab_pdf_system_extract._parse_all_blood_rows = _parse_rows_with_urinalysis
