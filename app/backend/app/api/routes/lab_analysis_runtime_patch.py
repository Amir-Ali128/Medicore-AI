"""Focused runtime fixes for the Phase 1 laboratory demo.

This module is imported by ``app.main`` after the API router is loaded. It keeps
changes isolated while correcting PDF parser collisions and ensuring that
frequently used laboratory parameters exist in fresh Render databases.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text as sql_text

from app.api.routes import lab_analysis as target


_EXTRA_PARAMETERS = [
    ("BUN", "BUN", "mg/dL"),
    ("KREATININ", "Kreatinin", "mg/dL"),
    ("BUN_KREATININ_ORANI", "BUN / Kreatinin", ""),
    ("NON_HDL", "Non-HDL", "mg/dL"),
    ("IG_MUTLAK", "IG Mutlak", "K/mm3"),
    ("IG_YUZDE", "IG %", "%"),
]


def _is_bun_creatinine_ratio_line(line: str) -> bool:
    normalized = target._normalize_text(line).upper().replace(" ", "")
    return any(
        marker in normalized
        for marker in (
            "BUN/KREATININ",
            "BUN/CREATININE",
            "BUNCREATININERATIO",
        )
    )


# Expand parser aliases used by common Turkish laboratory reports.
target.LAB_PARAMETER_ALIASES["Non-HDL"]["aliases"] = [
    "NON-HDL",
    "NON HDL",
    "NON-HDL KOLESTEROL",
    "NON HDL KOLESTEROL",
    "NON-HDL-KOLESTEROL",
    "NON HDL CHOLESTEROL",
    "NON-HDL CHOLESTEROL",
]
target.LAB_PARAMETER_ALIASES["IG Mutlak"]["aliases"] = [
    "IG MUTLAK",
    "IG ABSOLUTE",
    "IMMATURE GRANULOCYTE ABSOLUTE",
    "IMMATUR GRANULOSIT",
    "İMMATÜR GRANÜLOSİT",
    "IG (IMMATUR GRANULOSIT)",
    "IG (İMMATÜR GRANÜLOSİT)",
]
target.LAB_PARAMETER_ALIASES["IG %"]["aliases"] = [
    "IG %",
    "IG YUZDE",
    "IG YÜZDE",
    "IMMATURE GRANULOCYTE %",
    "IG (IMMATUR GRANULOSIT) %",
    "IG (İMMATÜR GRANÜLOSİT) %",
]


_original_find_parameter_value = target._find_parameter_value_in_lines


def _find_parameter_value_without_ratio_collision(
    *,
    raw_parameter_name: str,
    aliases: list[str],
    default_unit: str,
    lines: list[str],
) -> dict[str, Any] | None:
    filtered_lines = lines
    if raw_parameter_name in {"BUN", "Kreatinin"}:
        filtered_lines = [
            line for line in lines if not _is_bun_creatinine_ratio_line(line)
        ]

    return _original_find_parameter_value(
        raw_parameter_name=raw_parameter_name,
        aliases=aliases,
        default_unit=default_unit,
        lines=filtered_lines,
    )


target._find_parameter_value_in_lines = _find_parameter_value_without_ratio_collision


_original_forced_reference = target._forced_demo_reference


def _forced_reference_with_common_markers(
    parameter_name: str,
) -> tuple[str, float, float] | None:
    extra_references = {
        "Non-HDL": ("mg/dL", 0.0, 120.0),
        "IG Mutlak": ("K/mm3", 0.0, 0.06),
        "IG %": ("%", 0.0, 0.6),
    }
    return extra_references.get(parameter_name) or _original_forced_reference(
        parameter_name
    )


target._forced_demo_reference = _forced_reference_with_common_markers


_original_ensure_parameters = target._ensure_render_demo_clinical_parameters


async def _ensure_parameters_with_common_markers(session: Any) -> None:
    await _original_ensure_parameters(session)

    for parameter_code, canonical_name, default_unit in _EXTRA_PARAMETERS:
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
                "parameter_code": parameter_code,
                "canonical_name": canonical_name,
            },
        )
        existing_id = existing.scalar_one_or_none()

        if existing_id is None:
            await session.execute(
                sql_text(
                    """
                    INSERT INTO clinical_parameters (
                        id,
                        parameter_code,
                        canonical_name,
                        default_unit,
                        active_phase1,
                        analysis_level,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :parameter_code,
                        :canonical_name,
                        :default_unit,
                        true,
                        (
                            SELECT enumlabel::analysis_level
                            FROM pg_enum
                            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                            WHERE pg_type.typname = 'analysis_level'
                              AND enumlabel <> 'L0'
                            ORDER BY enumsortorder
                            LIMIT 1
                        ),
                        '{"source":"render_upload_runtime_patch"}'::jsonb,
                        NOW(),
                        NOW()
                    )
                    """
                ),
                {
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            f"medicore-demo:{parameter_code}",
                        )
                    ),
                    "parameter_code": parameter_code,
                    "canonical_name": canonical_name,
                    "default_unit": default_unit,
                },
            )
        else:
            await session.execute(
                sql_text(
                    """
                    UPDATE clinical_parameters
                    SET
                        parameter_code = :parameter_code,
                        canonical_name = :canonical_name,
                        default_unit = COALESCE(default_unit, :default_unit),
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
                    "parameter_code": parameter_code,
                    "canonical_name": canonical_name,
                    "default_unit": default_unit,
                },
            )


target._ensure_render_demo_clinical_parameters = (
    _ensure_parameters_with_common_markers
)
