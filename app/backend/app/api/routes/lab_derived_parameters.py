"""Derived laboratory parameters used by the Phase 1 PDF flow.

The source report may provide BUN directly or may provide only urea.  This
module keeps the calculation deterministic and prevents the parser from
reusing a neighbouring reference range for the ratio.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text as sql_text

from app.api.routes import lab_analysis


_RATIO_NAME = "BUN / Kreatinin"
_UREA_NAME = "Üre"
_RATIO_MIN = 10.0
_RATIO_MAX = 20.0
_UREA_TO_BUN_DIVISOR = 2.14


lab_analysis.LAB_PARAMETER_ALIASES.setdefault(
    _UREA_NAME,
    {
        "aliases": ["URE", "ÜRE", "UREA"],
        "default_unit": "mg/dL",
    },
)

_original_parse_lab_values = lab_analysis._parse_lab_values_from_text
_original_ensure_parameters = lab_analysis._ensure_render_demo_clinical_parameters


async def _ensure_parameters_with_urea(session: Any) -> None:
    await _original_ensure_parameters(session)

    existing = await session.execute(
        sql_text(
            """
            SELECT id
            FROM clinical_parameters
            WHERE parameter_code = 'UREA'
               OR canonical_name = :canonical_name
            LIMIT 1
            """
        ),
        {"canonical_name": _UREA_NAME},
    )
    existing_id = existing.scalar_one_or_none()

    if existing_id is None:
        await session.execute(
            sql_text(
                """
                INSERT INTO clinical_parameters (
                    id, parameter_code, canonical_name, default_unit,
                    active_phase1, analysis_level, metadata_json,
                    created_at, updated_at
                )
                VALUES (
                    :id, 'UREA', :canonical_name, 'mg/dL', true,
                    (
                        SELECT enumlabel::analysis_level
                        FROM pg_enum
                        JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                        WHERE pg_type.typname = 'analysis_level'
                          AND enumlabel <> 'L0'
                        ORDER BY enumsortorder
                        LIMIT 1
                    ),
                    '{"source":"derived_parameter_bootstrap"}'::jsonb,
                    NOW(), NOW()
                )
                """
            ),
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "medicore-demo:UREA")),
                "canonical_name": _UREA_NAME,
            },
        )
    else:
        await session.execute(
            sql_text(
                """
                UPDATE clinical_parameters
                SET parameter_code = 'UREA',
                    canonical_name = :canonical_name,
                    default_unit = COALESCE(default_unit, 'mg/dL'),
                    active_phase1 = true,
                    updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"id": existing_id, "canonical_name": _UREA_NAME},
        )


lab_analysis._ensure_render_demo_clinical_parameters = _ensure_parameters_with_urea


def _number(values: dict[str, dict[str, Any]], name: str) -> float | None:
    item = values.get(name)
    if item is None:
        return None
    try:
        return float(item["normalized_value"])
    except (KeyError, TypeError, ValueError):
        return None


def _parse_with_derived_ratio(text: str) -> list[dict[str, Any]]:
    parsed = _original_parse_lab_values(text)

    # A reported ratio can inherit the BUN range from the same PDF row layout.
    # Always replace it with a deterministic calculation from the base values.
    parsed = [item for item in parsed if item.get("raw_parameter_name") != _RATIO_NAME]
    by_name = {str(item.get("raw_parameter_name")): item for item in parsed}

    creatinine = _number(by_name, "Kreatinin")
    bun = _number(by_name, "BUN")
    urea = _number(by_name, _UREA_NAME)

    if creatinine is None or creatinine <= 0:
        return parsed

    ratio_source = "BUN"
    if bun is None and urea is not None:
        bun = urea / _UREA_TO_BUN_DIVISOR
        ratio_source = "Üre üzerinden hesaplanan BUN"

    if bun is None:
        return parsed

    ratio = round(bun / creatinine, 2)
    parsed.append(
        {
            "raw_parameter_name": _RATIO_NAME,
            "raw_value": str(ratio),
            "normalized_value": ratio,
            "unit": "",
            "extracted_reference_min": _RATIO_MIN,
            "extracted_reference_max": _RATIO_MAX,
            "extracted_unit": "",
            "measured_at": date.today().isoformat(),
            "metadata": {
                "derived": True,
                "formula": "BUN / Kreatinin",
                "source": ratio_source,
            },
        }
    )
    return parsed


lab_analysis._parse_lab_values_from_text = _parse_with_derived_ratio
