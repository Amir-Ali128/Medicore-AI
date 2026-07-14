"""Ensure serum globulin resolves to Globulin instead of thyroglobulin.

The fuzzy alias layer can otherwise bind ``GLOBULIN, Serum`` to the existing
thyroglobulin parameter.  This module registers an exact Phase 1 parameter and
keeps the correction deterministic for fresh and existing Render databases.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text as sql_text

from app.api.routes import lab_analysis


_PARAMETER_CODE = "GLOBULIN"
_CANONICAL_NAME = "Globulin"
_DEFAULT_UNIT = "g/dL"

lab_analysis.LAB_PARAMETER_ALIASES[_CANONICAL_NAME] = {
    "aliases": [
        "GLOBULIN, SERUM",
        "GLOBÜLİN, SERUM",
        "GLOBULIN SERUM",
        "GLOBÜLİN SERUM",
        "GLOBULIN",
        "GLOBÜLİN",
    ],
    "default_unit": _DEFAULT_UNIT,
}

_original_ensure_parameters = lab_analysis._ensure_render_demo_clinical_parameters


async def _ensure_globulin_parameter(session: Any) -> None:
    await _original_ensure_parameters(session)

    existing = await session.execute(
        sql_text(
            """
            SELECT id
            FROM clinical_parameters
            WHERE parameter_code = :parameter_code
               OR canonical_name = :canonical_name
            LIMIT 1
            """
        ),
        {
            "parameter_code": _PARAMETER_CODE,
            "canonical_name": _CANONICAL_NAME,
        },
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
                    :id, :parameter_code, :canonical_name, :default_unit, true,
                    (
                        SELECT enumlabel::analysis_level
                        FROM pg_enum
                        JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                        WHERE pg_type.typname = 'analysis_level'
                          AND enumlabel <> 'L0'
                        ORDER BY enumsortorder
                        LIMIT 1
                    ),
                    '{"source":"globulin_exact_mapping"}'::jsonb,
                    NOW(), NOW()
                )
                """
            ),
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "medicore:GLOBULIN")),
                "parameter_code": _PARAMETER_CODE,
                "canonical_name": _CANONICAL_NAME,
                "default_unit": _DEFAULT_UNIT,
            },
        )
    else:
        await session.execute(
            sql_text(
                """
                UPDATE clinical_parameters
                SET parameter_code = :parameter_code,
                    canonical_name = :canonical_name,
                    default_unit = :default_unit,
                    active_phase1 = true,
                    analysis_level = (
                        SELECT enumlabel::analysis_level
                        FROM pg_enum
                        JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                        WHERE pg_type.typname = 'analysis_level'
                          AND enumlabel <> 'L0'
                        ORDER BY enumsortorder
                        LIMIT 1
                    ),
                    updated_at = NOW()
                WHERE id = :id
                """
            ),
            {
                "id": existing_id,
                "parameter_code": _PARAMETER_CODE,
                "canonical_name": _CANONICAL_NAME,
                "default_unit": _DEFAULT_UNIT,
            },
        )


lab_analysis._ensure_render_demo_clinical_parameters = _ensure_globulin_parameter
