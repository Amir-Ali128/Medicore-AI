"""Seed missing lab parameters for the PDF upload demo.

Run from backend root:

    python scripts/seed_missing_lab_parameters.py

This script adds/updates a small set of clinical_parameters and reference_ranges
that are needed by the current PDF parser but are missing from the base
reference_ranges.csv seed.

It intentionally does not touch parameter_aliases.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.infrastructure.database import session


def make_parameter_code(name: str) -> str:
    replacements = {
        "ı": "i",
        "İ": "I",
        "ğ": "g",
        "Ğ": "G",
        "ü": "u",
        "Ü": "U",
        "ş": "s",
        "Ş": "S",
        "ö": "o",
        "Ö": "O",
        "ç": "c",
        "Ç": "C",
    }

    for source, target in replacements.items():
        name = name.replace(source, target)

    code = re.sub(r"[^A-Za-z0-9]+", "_", name)
    code = code.strip("_").upper()

    return code[:64]


def dec(value: str | int | float | None) -> Decimal | None:
    if value is None or value == "":
        return None

    return Decimal(str(value))


MISSING_PARAMETERS: list[dict[str, Any]] = [
    {
        "parameter_name": "GFR",
        "category": "Böbrek / Metabolik",
        "unit": "mL/dk/1.73m2",
        "adult_male_min": "60",
        "adult_male_max": "999",
        "adult_female_min": "60",
        "adult_female_max": "999",
        "child_min": "60",
        "child_max": "999",
        "elderly_male_min": "60",
        "elderly_male_max": "999",
        "elderly_female_min": "60",
        "elderly_female_max": "999",
        "reference_source": "Local demo seed; PDF decision threshold >60",
    },
    {
        "parameter_name": "Trigliserit",
        "category": "Lipid Paneli",
        "unit": "mg/dL",
        "adult_male_min": "0",
        "adult_male_max": "150",
        "adult_female_min": "0",
        "adult_female_max": "150",
        "child_min": "0",
        "child_max": "150",
        "elderly_male_min": "0",
        "elderly_male_max": "150",
        "elderly_female_min": "0",
        "elderly_female_max": "150",
        "reference_source": "Local demo seed; PDF decision threshold <150",
    },
    {
        "parameter_name": "FT3",
        "category": "Tiroid",
        "unit": "pmol/L",
        "adult_male_min": "3.93",
        "adult_male_max": "7.70",
        "adult_female_min": "3.93",
        "adult_female_max": "7.70",
        "child_min": "3.93",
        "child_max": "7.70",
        "elderly_male_min": "3.93",
        "elderly_male_max": "7.70",
        "elderly_female_min": "3.93",
        "elderly_female_max": "7.70",
        "reference_source": "Local demo seed; PDF reference range",
    },
    {
        "parameter_name": "FT4",
        "category": "Tiroid",
        "unit": "pmol/L",
        "adult_male_min": "12.00",
        "adult_male_max": "22.00",
        "adult_female_min": "12.00",
        "adult_female_max": "22.00",
        "child_min": "12.00",
        "child_max": "22.00",
        "elderly_male_min": "12.00",
        "elderly_male_max": "22.00",
        "elderly_female_min": "12.00",
        "elderly_female_max": "22.00",
        "reference_source": "Local demo seed; PDF reference range",
    },
    {
        "parameter_name": "Vitamin B1",
        "category": "Vitamin",
        "unit": "ug/L",
        "adult_male_min": "25.00",
        "adult_male_max": "75.00",
        "adult_female_min": "25.00",
        "adult_female_max": "75.00",
        "child_min": "25.00",
        "child_max": "75.00",
        "elderly_male_min": "25.00",
        "elderly_male_max": "75.00",
        "elderly_female_min": "25.00",
        "elderly_female_max": "75.00",
        "reference_source": "Local demo seed; PDF reference range",
    },
    {
        "parameter_name": "Sedimentasyon",
        "category": "İnflamasyon",
        "unit": "mm/S",
        "adult_male_min": "0.00",
        "adult_male_max": "15.00",
        "adult_female_min": "0.00",
        "adult_female_max": "15.00",
        "child_min": "0.00",
        "child_max": "15.00",
        "elderly_male_min": "0.00",
        "elderly_male_max": "15.00",
        "elderly_female_min": "0.00",
        "elderly_female_max": "15.00",
        "reference_source": "Local demo seed; PDF reference range",
    },
    {
        "parameter_name": "Folik Asit",
        "category": "Vitamin",
        "unit": "ng/mL",
        "adult_male_min": "3.89",
        "adult_male_max": "26.80",
        "adult_female_min": "3.89",
        "adult_female_max": "26.80",
        "child_min": "3.89",
        "child_max": "26.80",
        "elderly_male_min": "3.89",
        "elderly_male_max": "26.80",
        "elderly_female_min": "3.89",
        "elderly_female_max": "26.80",
        "reference_source": "Local demo seed; PDF reference range",
    },
    {
        "parameter_name": "P-LCR",
        "category": "Tam Kan Sayımı",
        "unit": "%",
        "adult_male_min": "19.40",
        "adult_male_max": "43.70",
        "adult_female_min": "19.40",
        "adult_female_max": "43.70",
        "child_min": "19.40",
        "child_max": "43.70",
        "elderly_male_min": "19.40",
        "elderly_male_max": "43.70",
        "elderly_female_min": "19.40",
        "elderly_female_max": "43.70",
        "reference_source": "Local demo seed; PDF reference range",
    },
]


async def get_default_analysis_level(conn):
    result = await conn.execute(
        text(
            """
            SELECT enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = 'analysis_level'
            ORDER BY enumsortorder
            LIMIT 1
            """
        )
    )

    analysis_level = result.scalar_one_or_none()

    if analysis_level is None:
        raise RuntimeError("analysis_level enum bulunamadı.")

    return analysis_level


async def upsert_clinical_parameter(conn, row: dict[str, Any], analysis_level: str):
    parameter_name = row["parameter_name"]
    parameter_code = make_parameter_code(parameter_name)

    metadata = {
        "clinical_note": "Added by seed_missing_lab_parameters.py for PDF upload demo.",
        "reference_source": row.get("reference_source", "Local demo seed"),
    }

    result = await conn.execute(
        text(
            """
            INSERT INTO clinical_parameters (
                id,
                canonical_name,
                parameter_code,
                default_unit,
                category,
                active_phase1,
                analysis_level,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :canonical_name,
                :parameter_code,
                :default_unit,
                :category,
                true,
                CAST(:analysis_level AS analysis_level),
                CAST(:metadata_json AS jsonb),
                NOW(),
                NOW()
            )
            ON CONFLICT (parameter_code)
            DO UPDATE SET
                canonical_name = EXCLUDED.canonical_name,
                default_unit = EXCLUDED.default_unit,
                category = EXCLUDED.category,
                active_phase1 = true,
                analysis_level = EXCLUDED.analysis_level,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = NOW()
            RETURNING id
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "canonical_name": parameter_name,
            "parameter_code": parameter_code,
            "default_unit": row["unit"],
            "category": row["category"],
            "analysis_level": analysis_level,
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        },
    )

    return result.scalar_one()


async def replace_reference_ranges(conn, parameter_id, row: dict[str, Any]):
    await conn.execute(
        text("DELETE FROM reference_ranges WHERE parameter_id = :parameter_id"),
        {"parameter_id": parameter_id},
    )

    range_specs = [
        ("male", 18, 64, False, "adult_male_min", "adult_male_max", "adult_male"),
        ("female", 18, 64, False, "adult_female_min", "adult_female_max", "adult_female"),
        ("any", 0, 17, False, "child_min", "child_max", "child"),
        ("male", 65, None, False, "elderly_male_min", "elderly_male_max", "elderly_male"),
        ("female", 65, None, False, "elderly_female_min", "elderly_female_max", "elderly_female"),
    ]

    inserted = 0

    for sex, age_min, age_max, pregnancy_status, min_key, max_key, label in range_specs:
        reference_min = dec(row.get(min_key))
        reference_max = dec(row.get(max_key))

        if reference_min is None and reference_max is None:
            continue

        metadata = {
            "range_label": label,
            "parameter_name": row["parameter_name"],
            "reference_source_full": row.get("reference_source", "Local demo seed"),
        }

        await conn.execute(
            text(
                """
                INSERT INTO reference_ranges (
                    id,
                    parameter_id,
                    sex,
                    age_min,
                    age_max,
                    pregnancy_status,
                    reference_min,
                    reference_max,
                    unit,
                    source,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :parameter_id,
                    CAST(:sex AS sex),
                    :age_min,
                    :age_max,
                    :pregnancy_status,
                    :reference_min,
                    :reference_max,
                    :unit,
                    :source,
                    CAST(:metadata_json AS jsonb),
                    NOW(),
                    NOW()
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "parameter_id": str(parameter_id),
                "sex": sex,
                "age_min": age_min,
                "age_max": age_max,
                "pregnancy_status": pregnancy_status,
                "reference_min": reference_min,
                "reference_max": reference_max,
                "unit": row["unit"],
                "source": "Local demo seed",
                "metadata_json": json.dumps(metadata, ensure_ascii=False),
            },
        )

        inserted += 1

    return inserted


async def main():
    engine = getattr(session, "async_engine", None) or getattr(session, "engine", None)

    if engine is None:
        raise RuntimeError("Database engine bulunamadı.")

    parameter_count = 0
    range_count = 0

    async with engine.begin() as conn:
        analysis_level = await get_default_analysis_level(conn)

        for row in MISSING_PARAMETERS:
            parameter_id = await upsert_clinical_parameter(conn, row, analysis_level)
            inserted_ranges = await replace_reference_ranges(conn, parameter_id, row)

            parameter_count += 1
            range_count += inserted_ranges

    await engine.dispose()

    print("Missing lab parameter seed tamamlandı.")
    print(f"Clinical parameters upserted: {parameter_count}")
    print(f"Reference ranges inserted: {range_count}")


if __name__ == "__main__":
    asyncio.run(main())