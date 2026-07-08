import asyncio
import csv
import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import text

from app.infrastructure.database import session


CSV_PATHS = [
    Path("app/data/reference_ranges.csv"),
    Path("app/data/reference_full_demographic_FINAL_v11.csv"),
]


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def to_decimal(value):
    value = clean(value)

    if not value or value.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None

    value = value.replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return None

    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def slugify_code(name):
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

    code = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return code[:64]


def find_csv_path():
    for path in CSV_PATHS:
        if path.exists():
            return path

    raise FileNotFoundError(
        "CSV not found. Expected app/data/reference_ranges.csv"
    )


async def get_first_enum_value(conn, enum_name):
    result = await conn.execute(
        text(
            """
            SELECT enumlabel
            FROM pg_enum
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = :enum_name
            ORDER BY enumsortorder
            LIMIT 1
            """
        ),
        {"enum_name": enum_name},
    )

    value = result.scalar_one_or_none()

    if value is None:
        raise RuntimeError(f"Enum not found or empty: {enum_name}")

    return value


async def upsert_parameter(conn, row, analysis_level):
    parameter_name = clean(row.get("parameter_name"))
    category = clean(row.get("category")) or "Uncategorized"
    unit = clean(row.get("unit")) or None
    parameter_code = slugify_code(parameter_name)

    metadata = {
        "is_qualitative": clean(row.get("is_qualitative")),
        "clinical_meaning_negative": clean(row.get("clinical_meaning_negative")),
        "clinical_meaning_positive": clean(row.get("clinical_meaning_positive")),
        "clinical_meaning_low": clean(row.get("clinical_meaning_low")),
        "clinical_meaning_normal": clean(row.get("clinical_meaning_normal")),
        "clinical_meaning_detected": clean(row.get("clinical_meaning_detected")),
        "clinical_meaning_undetected": clean(row.get("clinical_meaning_undetected")),
        "clinical_note": clean(row.get("clinical_note")),
        "pregnancy_week_ranges": clean(row.get("pregnancy_week_ranges")),
        "interpretation_thresholds": clean(row.get("interpretation_thresholds")),
        "cycle_phase_ranges": clean(row.get("cycle_phase_ranges")),
        "age_band_ranges": clean(row.get("age_band_ranges")),
        "ratio_interpretation": clean(row.get("ratio_interpretation")),
        "assay_specific_99th_percentile": clean(row.get("assay_specific_99th_percentile")),
        "unit_system_variants": clean(row.get("unit_system_variants")),
        "missing_data_flags": clean(row.get("missing_data_flags")),
        "last_updated": clean(row.get("last_updated")),
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
            "default_unit": unit,
            "category": category,
            "analysis_level": analysis_level,
            "metadata_json": json.dumps(metadata),
        },
    )

    return result.scalar_one()


async def insert_reference_ranges(conn, parameter_id, row):
    await conn.execute(
        text("DELETE FROM reference_ranges WHERE parameter_id = :parameter_id"),
        {"parameter_id": parameter_id},
    )

    unit = clean(row.get("unit")) or None
    source = clean(row.get("reference_source")) or "CSV"

    bands = [
        {
            "label": "adult_male",
            "sex": "male",
            "age_min": 18,
            "age_max": 64,
            "pregnancy_status": False,
            "min_col": "adult_male_min",
            "max_col": "adult_male_max",
        },
        {
            "label": "adult_female",
            "sex": "female",
            "age_min": 18,
            "age_max": 64,
            "pregnancy_status": False,
            "min_col": "adult_female_min",
            "max_col": "adult_female_max",
        },
        {
            "label": "child",
            "sex": "any",
            "age_min": 0,
            "age_max": 17,
            "pregnancy_status": False,
            "min_col": "child_min",
            "max_col": "child_max",
        },
        {
            "label": "elderly_male",
            "sex": "male",
            "age_min": 65,
            "age_max": None,
            "pregnancy_status": False,
            "min_col": "elderly_male_min",
            "max_col": "elderly_male_max",
        },
        {
            "label": "elderly_female",
            "sex": "female",
            "age_min": 65,
            "age_max": None,
            "pregnancy_status": False,
            "min_col": "elderly_female_min",
            "max_col": "elderly_female_max",
        },
        {
            "label": "pregnant",
            "sex": "female",
            "age_min": 18,
            "age_max": 50,
            "pregnancy_status": True,
            "min_col": "pregnant_min",
            "max_col": "pregnant_max",
        },
    ]

    inserted = 0

    for band in bands:
        reference_min = to_decimal(row.get(band["min_col"]))
        reference_max = to_decimal(row.get(band["max_col"]))

        if reference_min is None and reference_max is None:
            continue

        metadata = {
            "band": band["label"],
            "parameter_name": clean(row.get("parameter_name")),
            "no_upper_limit": clean(row.get("no_upper_limit")),
            "detection_limit": clean(row.get("detection_limit")),
            "source_csv": "reference_ranges.csv",
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
                "sex": band["sex"],
                "age_min": band["age_min"],
                "age_max": band["age_max"],
                "pregnancy_status": band["pregnancy_status"],
                "reference_min": reference_min,
                "reference_max": reference_max,
                "unit": unit,
                "source": source,
                "metadata_json": json.dumps(metadata),
            },
        )

        inserted += 1

    return inserted


async def main():
    csv_path = find_csv_path()

    engine = (
        getattr(session, "async_engine", None)
        or getattr(session, "engine", None)
    )

    if engine is None:
        raise RuntimeError("Could not find SQLAlchemy async engine.")

    parameter_count = 0
    range_count = 0

    async with engine.begin() as conn:
        analysis_level = await get_first_enum_value(conn, "analysis_level")

        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            for row in reader:
                parameter_name = clean(row.get("parameter_name"))

                if not parameter_name:
                    continue

                parameter_id = await upsert_parameter(conn, row, analysis_level)
                inserted_ranges = await insert_reference_ranges(conn, parameter_id, row)

                parameter_count += 1
                range_count += inserted_ranges

    await engine.dispose()

    print(f"CSV imported: {csv_path}")
    print(f"Clinical parameters processed: {parameter_count}")
    print(f"Reference ranges inserted: {range_count}")


if __name__ == "__main__":
    asyncio.run(main())
