import asyncio
import csv
import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import text

from app.infrastructure.database import session


CSV_PATH = Path("app/data/reference_ranges.csv")


def clean(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in {"", "nan", "none", "null", "n/a", "na", "-"}:
        return ""

    return value


def truncate(value, max_length):
    value = clean(value)

    if not value:
        return None

    return value[:max_length]


def to_decimal(value):
    value = clean(value)

    if not value:
        return None

    value = value.replace(",", ".")

    match = re.search(r"-?\d+(?:\.\d+)?", value)

    if not match:
        return None

    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def make_parameter_code(name):
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


async def upsert_clinical_parameter(conn, row, analysis_level):
    parameter_name = clean(row.get("parameter_name"))

    if not parameter_name:
        return None

    parameter_code = make_parameter_code(parameter_name)
    category = truncate(row.get("category"), 128) or "Uncategorized"
    unit = truncate(row.get("unit"), 64)

    metadata = {
        "is_qualitative": clean(row.get("is_qualitative")),
        "clinical_meaning_negative": clean(row.get("clinical_meaning_negative")),
        "clinical_meaning_positive": clean(row.get("clinical_meaning_positive")),
        "clinical_meaning_low": clean(row.get("clinical_meaning_low")),
        "clinical_meaning_normal": clean(row.get("clinical_meaning_normal")),
        "clinical_meaning_detected": clean(row.get("clinical_meaning_detected")),
        "clinical_meaning_undetected": clean(row.get("clinical_meaning_undetected")),
        "clinical_note": clean(row.get("clinical_note")),
        "reference_source": clean(row.get("reference_source")),
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
            "canonical_name": truncate(parameter_name, 255),
            "parameter_code": parameter_code,
            "default_unit": unit,
            "category": category,
            "analysis_level": analysis_level,
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        },
    )

    return result.scalar_one()


async def replace_reference_ranges(conn, parameter_id, row):
    await conn.execute(
        text("DELETE FROM reference_ranges WHERE parameter_id = :parameter_id"),
        {"parameter_id": parameter_id},
    )

    unit = truncate(row.get("unit"), 64)

    full_source = clean(row.get("reference_source")) or "CSV"
    source = full_source[:128]

    ranges = [
        {
            "sex": "male",
            "age_min": 18,
            "age_max": 64,
            "pregnancy_status": False,
            "min_column": "adult_male_min",
            "max_column": "adult_male_max",
            "label": "adult_male",
        },
        {
            "sex": "female",
            "age_min": 18,
            "age_max": 64,
            "pregnancy_status": False,
            "min_column": "adult_female_min",
            "max_column": "adult_female_max",
            "label": "adult_female",
        },
        {
            "sex": "any",
            "age_min": 0,
            "age_max": 17,
            "pregnancy_status": False,
            "min_column": "child_min",
            "max_column": "child_max",
            "label": "child",
        },
        {
            "sex": "male",
            "age_min": 65,
            "age_max": None,
            "pregnancy_status": False,
            "min_column": "elderly_male_min",
            "max_column": "elderly_male_max",
            "label": "elderly_male",
        },
        {
            "sex": "female",
            "age_min": 65,
            "age_max": None,
            "pregnancy_status": False,
            "min_column": "elderly_female_min",
            "max_column": "elderly_female_max",
            "label": "elderly_female",
        },
        {
            "sex": "female",
            "age_min": 18,
            "age_max": 50,
            "pregnancy_status": True,
            "min_column": "pregnant_min",
            "max_column": "pregnant_max",
            "label": "pregnant",
        },
    ]

    inserted_count = 0

    for item in ranges:
        reference_min = to_decimal(row.get(item["min_column"]))
        reference_max = to_decimal(row.get(item["max_column"]))

        if reference_min is None and reference_max is None:
            continue

        metadata = {
            "range_label": item["label"],
            "parameter_name": clean(row.get("parameter_name")),
            "no_upper_limit": clean(row.get("no_upper_limit")),
            "detection_limit": clean(row.get("detection_limit")),
            "reference_source_full": full_source,
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
                "sex": item["sex"],
                "age_min": item["age_min"],
                "age_max": item["age_max"],
                "pregnancy_status": item["pregnancy_status"],
                "reference_min": reference_min,
                "reference_max": reference_max,
                "unit": unit,
                "source": source,
                "metadata_json": json.dumps(metadata, ensure_ascii=False),
            },
        )

        inserted_count += 1

    return inserted_count


async def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV bulunamadı: {CSV_PATH}")

    engine = getattr(session, "async_engine", None) or getattr(session, "engine", None)

    if engine is None:
        raise RuntimeError("Database engine bulunamadı.")

    parameter_count = 0
    range_count = 0

    async with engine.begin() as conn:
        analysis_level = await get_default_analysis_level(conn)

        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            for row in reader:
                parameter_id = await upsert_clinical_parameter(
                    conn,
                    row,
                    analysis_level,
                )

                if parameter_id is None:
                    continue

                inserted_ranges = await replace_reference_ranges(conn, parameter_id, row)

                parameter_count += 1
                range_count += inserted_ranges

    await engine.dispose()

    print("Reference data seed tamamlandı.")
    print(f"CSV: {CSV_PATH}")
    print(f"Clinical parameters: {parameter_count}")
    print(f"Reference ranges: {range_count}")


if __name__ == "__main__":
    asyncio.run(main())







