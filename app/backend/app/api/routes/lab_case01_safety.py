"""Deterministic safety fixes for the Phase 1 synthetic renal/dehydration case.

This module is imported for side effects during application startup. It keeps
common renal/acid-base values in the deterministic backend path and augments the
compact AI route with a backend-generated prerenal/dehydration review pattern.

The LLM still receives only short symptoms + flags; raw values/reference ranges
remain backend-only.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text as sql_text

from app.api.routes import lab_analysis
from app.domain import alias_engine
from app.domain.claude_clinical_hypothesis_service import (
    ClaudeClinicalHypothesisService,
)


# Common aliases seen in synthetic cards, manually entered cases, and English
# exports. These targets resolve to deterministic clinical parameters.
_CURATED_ALIASES: dict[str, tuple[str, ...]] = {
    "Kan Üre Nitrojeni (BUN)": ("BUN", "Blood Urea Nitrogen"),
    "Kan Üre Nitrojeni": ("BUN", "Blood Urea Nitrogen"),
    "Kan Üre Nitrojen (BUN)": ("BUN", "Blood Urea Nitrogen"),
    "Blood Urea Nitrogen": ("BUN", "Blood Urea Nitrogen"),
    "Bicarbonate (HCO3)": ("HCO3", "HCO3 (Bikarbonat)", "Bikarbonat"),
    "Bikarbonat (HCO3)": ("HCO3", "HCO3 (Bikarbonat)", "Bikarbonat"),
    "HCO3": ("HCO3", "HCO3 (Bikarbonat)", "Bikarbonat"),
    "Anion Gap": ("ANION_GAP", "Anyon Açığı", "Anion Gap"),
    "Anyon Açığı": ("ANION_GAP", "Anyon Açığı", "Anion Gap"),
    "Anyon Acigi": ("ANION_GAP", "Anyon Açığı", "Anion Gap"),
}

alias_engine._CURATED_ALIAS_TARGETS_RAW.update(_CURATED_ALIASES)
alias_engine._CURATED_ALIAS_TARGETS.update(
    {
        alias_engine.normalize_alias(raw): tuple(targets)
        for raw, targets in _CURATED_ALIASES.items()
    }
)


# Parser-side aliases. setdefault preserves any future upstream definition.
lab_analysis.LAB_PARAMETER_ALIASES.setdefault(
    "HCO3 (Bikarbonat)",
    {
        "aliases": [
            "BICARBONATE (HCO3)",
            "BIKARBONAT (HCO3)",
            "HCO3 (BIKARBONAT)",
            "BICARBONATE",
            "BIKARBONAT",
            "HCO3",
        ],
        "default_unit": "mEq/L",
    },
)
lab_analysis.LAB_PARAMETER_ALIASES.setdefault(
    "Anyon Açığı",
    {
        "aliases": ["ANION GAP", "ANYON ACIGI", "ANYON AÇIĞI"],
        "default_unit": "mEq/L",
    },
)


# Generic fallback ranges are used only after an extracted report range and a
# compatible demographic DB range fail. They make the synthetic card fully
# deterministic without asking the LLM to compare numbers.
_PARAMETER_SPECS: tuple[tuple[str, str, str, float, float], ...] = (
    ("BUN", "BUN", "mg/dL", 7.0, 20.0),
    ("HCO3", "HCO3 (Bikarbonat)", "mEq/L", 22.0, 26.0),
    ("ANION_GAP", "Anyon Açığı", "mEq/L", 8.0, 16.0),
)

_original_ensure_parameters = lab_analysis._ensure_render_demo_clinical_parameters


async def _ensure_case01_parameters(session: Any) -> None:
    await _original_ensure_parameters(session)

    for code, canonical_name, unit, lower, upper in _PARAMETER_SPECS:
        existing = await session.execute(
            sql_text(
                """
                SELECT id
                FROM clinical_parameters
                WHERE parameter_code = :code OR canonical_name = :canonical_name
                LIMIT 1
                """
            ),
            {"code": code, "canonical_name": canonical_name},
        )
        parameter_id = existing.scalar_one_or_none()

        if parameter_id is None:
            parameter_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"medicore-case01:{code}")
            await session.execute(
                sql_text(
                    """
                    INSERT INTO clinical_parameters (
                        id, parameter_code, canonical_name, default_unit,
                        active_phase1, analysis_level, metadata_json,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, :code, :canonical_name, :unit, true,
                        (
                            SELECT enumlabel::analysis_level
                            FROM pg_enum
                            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                            WHERE pg_type.typname = 'analysis_level'
                              AND enumlabel <> 'L0'
                            ORDER BY enumsortorder
                            LIMIT 1
                        ),
                        '{"source":"case01_deterministic_bootstrap"}'::jsonb,
                        NOW(), NOW()
                    )
                    """
                ),
                {
                    "id": str(parameter_id),
                    "code": code,
                    "canonical_name": canonical_name,
                    "unit": unit,
                },
            )
        else:
            await session.execute(
                sql_text(
                    """
                    UPDATE clinical_parameters
                    SET parameter_code = :code,
                        canonical_name = :canonical_name,
                        default_unit = COALESCE(default_unit, :unit),
                        active_phase1 = true,
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": parameter_id,
                    "code": code,
                    "canonical_name": canonical_name,
                    "unit": unit,
                },
            )

        generic = await session.execute(
            sql_text(
                """
                SELECT id
                FROM reference_ranges
                WHERE parameter_id = :parameter_id
                  AND sex = 'any'::sex
                  AND age_min IS NULL
                  AND age_max IS NULL
                  AND pregnancy_status IS NULL
                LIMIT 1
                """
            ),
            {"parameter_id": parameter_id},
        )
        generic_id = generic.scalar_one_or_none()

        if generic_id is None:
            generic_id = uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"medicore-case01-reference:{code}",
            )
            await session.execute(
                sql_text(
                    """
                    INSERT INTO reference_ranges (
                        id, parameter_id, sex, age_min, age_max,
                        pregnancy_status, reference_min, reference_max,
                        unit, source, metadata_json, created_at, updated_at
                    )
                    VALUES (
                        :id, :parameter_id, 'any'::sex, NULL, NULL,
                        NULL, :lower, :upper, :unit,
                        'MediCore synthetic-card deterministic fallback',
                        '{"scope":"phase1_synthetic_case","lab_specific_range_preferred":true}'::jsonb,
                        NOW(), NOW()
                    )
                    """
                ),
                {
                    "id": str(generic_id),
                    "parameter_id": parameter_id,
                    "lower": lower,
                    "upper": upper,
                    "unit": unit,
                },
            )


lab_analysis._ensure_render_demo_clinical_parameters = _ensure_case01_parameters


_DEHYDRATION_TERMS = (
    "dehidrat",
    "kusma",
    "kustu",
    "sivi alimi",
    "sıvı alımı",
    "azalmis sivi",
    "azalmış sıvı",
    "agiz kurulugu",
    "ağız kuruluğu",
    "mukoza kuru",
    "mukozalar kuru",
    "idrar az",
    "idrar miktarinda azalma",
    "idrar miktarında azalma",
    "oliguri",
    "vomit",
    "reduced fluid",
    "poor oral intake",
    "dry mouth",
    "dry mucosa",
    "decreased urine",
    "oliguria",
)

_RENAL_PATTERN_PREFIXES = (
    "BUN_HIGH",
    "UREA_HIGH",
    "URE_HIGH",
    "KREATININ_HIGH",
    "CREATININE_HIGH",
    "BUN_KREATININ_ORANI_HIGH",
    "BUN_KREATININ_HIGH",
    "BUN_CREATININE_RATIO_HIGH",
    "GFR_LOW",
    "EGFR_LOW",
    "SODYUM_HIGH",
    "SODIUM_HIGH",
)


def _fold(text: str) -> str:
    return " ".join(text.lower().split())


def has_dehydration_symptoms(symptoms: list[str]) -> bool:
    haystack = " ".join(_fold(item) for item in symptoms if item)
    return any(term in haystack for term in _DEHYDRATION_TERMS)


def should_add_prerenal_pattern(flags: list[str], symptoms: list[str]) -> bool:
    renal_hits = {
        prefix
        for prefix in _RENAL_PATTERN_PREFIXES
        if any(flag == prefix or flag.startswith(prefix + "_") for flag in flags)
    }
    return len(renal_hits) >= 3 and has_dehydration_symptoms(symptoms)


_original_build_user_prompt = ClaudeClinicalHypothesisService._build_user_prompt
_original_fallback_output = ClaudeClinicalHypothesisService._fallback_output


def _build_user_prompt_with_patterns(
    symptoms: list[str], flags: list[str], language: str
) -> str:
    if has_dehydration_symptoms(symptoms) and "DEHYDRATION_SYMPTOMS" not in flags:
        flags.append("DEHYDRATION_SYMPTOMS")

    if (
        should_add_prerenal_pattern(flags, symptoms)
        and "PRERENAL_DEHYDRATION_PATTERN_REVIEW" not in flags
    ):
        flags.append("PRERENAL_DEHYDRATION_PATTERN_REVIEW")

    return _original_build_user_prompt(symptoms, flags, language)


def _fallback_output_with_patterns(flags: list[str], language: str) -> tuple[int, str]:
    if "PRERENAL_DEHYDRATION_PATTERN_REVIEW" in flags:
        if language.lower().startswith("tr"):
            return (
                2,
                "Dehidratasyonla uyumlu prerenal patern için hekim değerlendirmesi gerekir.",
            )
        return 2, "A dehydration-compatible prerenal pattern requires physician review."
    return _original_fallback_output(flags, language)


ClaudeClinicalHypothesisService._build_user_prompt = staticmethod(
    _build_user_prompt_with_patterns
)
ClaudeClinicalHypothesisService._fallback_output = staticmethod(
    _fallback_output_with_patterns
)
