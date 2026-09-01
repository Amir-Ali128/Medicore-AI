"""Runtime corrections for full PDF blood-row extraction.

Keeps absolute (#) and percentage (%) CBC rows distinct and filters page/footer
numbers before they can be interpreted as laboratory tests.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.api.routes import lab_analysis, lab_pdf_system_extract


def _name_key(value: str) -> str:
    normalized = lab_analysis._normalize_text(value).upper()
    normalized = normalized.replace("#", " ABS ").replace("%", " PCT ")
    return re.sub(r"[^A-Z0-9]+", "", normalized)


_original_numeric_row = lab_pdf_system_extract._row_from_numeric_match


def _row_from_numeric_match(
    match: re.Match[str],
    report_date: date,
) -> dict[str, Any] | None:
    row = _original_numeric_row(match, report_date)
    if row is None:
        return None
    name = str(row.get("display_name") or "").strip()
    if name.startswith("0 850") or name.lower().startswith("sayfa"):
        return None
    return row


lab_pdf_system_extract._name_key = _name_key
lab_pdf_system_extract._row_from_numeric_match = _row_from_numeric_match
