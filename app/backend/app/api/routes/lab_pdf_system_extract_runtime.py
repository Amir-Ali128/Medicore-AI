"""Runtime corrections for full PDF blood-row extraction.

Keeps absolute (#) and percentage (%) CBC rows distinct, prevents rows without a
printed reference interval from crashing the upload flow, filters page/footer
numbers, and batches dynamic parameter creation to avoid excessive DB round trips.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import text as sql_text

from app.api.routes import lab_analysis, lab_pdf_system_extract
from app.infrastructure.database.session import AsyncSessionFactory


def _name_key(value: str) -> str:
    normalized = lab_analysis._normalize_text(value).upper()
    normalized = normalized.replace("#", " ABS ").replace("%", " PCT ")
    return re.sub(r"[^A-Z0-9]+", "", normalized)


_original_numeric_row = lab_pdf_system_extract._row_from_numeric_match


def _row_from_numeric_match(
    match: re.Match[str],
    report_date: date,
) -> dict[str, Any] | None:
    groups = match.groupdict()

    # _NUMERIC_NO_REFERENCE_RE intentionally has no ``unit`` or ``reference``
    # group. The base parser used to pass such rows into a helper that expected
    # both groups, causing IndexError and surfacing as "Failed to fetch" in the
    # browser. Preserve the test with an empty unit/range so MediCore can fall
    # back to a stored reference if one exists; otherwise it remains reviewable.
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
    """Create unseen PDF parameters in one DB batch instead of row by row."""
    dynamic_rows = [row for row in rows if row.get("dynamic") is True]
    if not dynamic_rows:
        return

    payloads: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for row in dynamic_rows:
        code = str(row.get("parameter_code") or "").strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        payloads.append(
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"medicore-pdf:{code}")),
                "code": code,
                "canonical": str(row.get("display_name") or code)[:255],
                "default_unit": str(row.get("unit") or "")[:64],
            }
        )

    if not payloads:
        return

    statement = sql_text(
        """
        INSERT INTO clinical_parameters (
            id, parameter_code, canonical_name, default_unit, category,
            active_phase1, analysis_level, metadata_json, created_at, updated_at
        )
        VALUES (
            :id, :code, :canonical, :default_unit, 'pdf_import', true,
            'L4'::analysis_level,
            '{"source":"pdf_report_dynamic_parameter","report_reference_preferred":true}'::jsonb,
            NOW(), NOW()
        )
        ON CONFLICT (parameter_code) DO NOTHING
        """
    )

    async with AsyncSessionFactory() as session:
        await session.execute(statement, payloads)
        await session.commit()


lab_pdf_system_extract._name_key = _name_key
lab_pdf_system_extract._row_from_numeric_match = _row_from_numeric_match
lab_pdf_system_extract._ensure_dynamic_parameters = _ensure_dynamic_parameters
