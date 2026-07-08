"""Reference-data import script.

Imports every parameter from the reference CSV into the database:

    * ALL parameters are stored (canonical parameter + aliases + demographic
      reference ranges).
    * Only the four Phase 1 groups are activated (active_phase1=True,
      analysis_level=L4); everything else is a passive dictionary record
      (active_phase1=False, analysis_level=L0).

The wide, column-per-demographic CSV rows are normalized into one
`ReferenceRange` per populated band. The demographic-to-(sex, age, pregnancy)
mapping is defined explicitly in `DEMOGRAPHIC_BANDS` so the age windows are
auditable and tunable rather than hidden magic numbers.

Run:  python -m app.scripts.import_reference_csv --csv path/to/reference.csv
The import is idempotent: re-running upserts parameters by code and rebuilds
their ranges.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.domain.normalization import normalize_alias
from app.domain.phase1_parameter_selector import (
    PASSIVE_LEVEL,
    phase1_selector,
)
from app.core.config import get_settings
from app.domain.enums import Sex
from app.infrastructure.database.models.reference_range import ReferenceRange
from app.infrastructure.database.repositories.clinical_parameter_repository import (
    ClinicalParameterRepository,
)
from app.infrastructure.database.repositories.parameter_alias_repository import (
    ParameterAliasRepository,
)
from app.infrastructure.database.repositories.reference_range_repository import (
    ReferenceRangeRepository,
)
from app.infrastructure.database.session import AsyncSessionFactory, engine

_settings = get_settings()

DEFAULT_CSV_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "reference_full_demographic_FINAL_v11.csv"
)

# CSV columns that hold numeric demographic bounds (excluded from metadata blob).
_RANGE_COLUMNS: frozenset[str] = frozenset(
    {
        "adult_male_min", "adult_male_max",
        "adult_female_min", "adult_female_max",
        "child_min", "child_max",
        "elderly_male_min", "elderly_male_max",
        "elderly_female_min", "elderly_female_max",
        "pregnant_min", "pregnant_max",
    }
)

# CSV columns that carry structured JSON payloads (parsed into metadata).
_JSON_COLUMNS: frozenset[str] = frozenset(
    {
        "pregnancy_week_ranges",
        "interpretation_thresholds",
        "cycle_phase_ranges",
        "age_band_ranges",
        "ratio_interpretation",
        "assay_specific_99th_percentile",
        "unit_system_variants",
        "missing_data_flags",
    }
)


@dataclass(frozen=True, slots=True)
class DemographicBand:
    """Maps a CSV demographic column pair onto a reference-range profile.

    Age windows (years) are explicit, auditable conventions derived from the
    CSV's coarse demographic bands; adjust here if clinical policy changes.
    """

    key: str
    min_column: str
    max_column: str
    sex: Sex
    age_min: float | None
    age_max: float | None
    pregnancy_status: bool | None


DEMOGRAPHIC_BANDS: tuple[DemographicBand, ...] = (
    DemographicBand("adult_male", "adult_male_min", "adult_male_max", Sex.MALE, 18.0, 65.0, None),
    DemographicBand("adult_female", "adult_female_min", "adult_female_max", Sex.FEMALE, 18.0, 65.0, False),
    DemographicBand("child", "child_min", "child_max", Sex.ANY, 0.0, 18.0, None),
    DemographicBand("elderly_male", "elderly_male_min", "elderly_male_max", Sex.MALE, 65.0, None, None),
    DemographicBand("elderly_female", "elderly_female_min", "elderly_female_max", Sex.FEMALE, 65.0, None, False),
    DemographicBand("pregnant", "pregnant_min", "pregnant_max", Sex.FEMALE, 18.0, 50.0, True),
)

_TRUE_TOKENS = {"true", "1", "yes", "evet", "y", "t"}
_FALSE_TOKENS = {"false", "0", "no", "hayir", "n", "f"}


@dataclass(slots=True)
class ImportStats:
    parameters: int = 0
    active: int = 0
    passive: int = 0
    aliases: int = 0
    ranges: int = 0


def _clean(value: str | None) -> str:
    return value.strip() if value else ""


def _parse_decimal(value: str | None) -> Decimal | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _parse_bool(value: str | None) -> bool | None:
    text = _clean(value).lower()
    if text in _TRUE_TOKENS:
        return True
    if text in _FALSE_TOKENS:
        return False
    return None


def _parse_json(value: str | None) -> Any:
    text = _clean(value)
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


def _slug_code(name: str) -> str:
    normalized = normalize_alias(name)
    slug = normalized.replace(" ", "_").upper()
    return slug or "PARAM"


def _build_metadata(row: dict[str, str], group: str | None) -> dict[str, Any]:
    """Collect non-range provenance/clinical metadata for a parameter."""
    source: dict[str, Any] = {}
    for column, raw in row.items():
        if column in _RANGE_COLUMNS or not _clean(raw):
            continue
        source[column] = _parse_json(raw) if column in _JSON_COLUMNS else raw.strip()

    return {
        "phase1_group": group,
        "is_qualitative": _parse_bool(row.get("is_qualitative")) or False,
        "no_upper_limit": _parse_bool(row.get("no_upper_limit")) or False,
        "reference_source": _clean(row.get("reference_source")) or None,
        "last_updated": _clean(row.get("last_updated")) or None,
        "source_row": source,
    }


def _load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


async def _import_row(
    row: dict[str, str],
    *,
    used_codes: set[str],
    cp_repo: ClinicalParameterRepository,
    alias_repo: ParameterAliasRepository,
    rr_repo: ReferenceRangeRepository,
    stats: ImportStats,
) -> None:
    name = _clean(row.get("parameter_name"))
    if not name:
        return

    match = phase1_selector.match(name, _clean(row.get("category")) or None)
    active = match is not None
    group = match.group if match else None

    # Stable, unique parameter_code.
    base_code = match.code if match else _slug_code(name)
    code = base_code
    suffix = 2
    while code in used_codes:
        code = f"{base_code}_{suffix}"
        suffix += 1
    used_codes.add(code)

    metadata = _build_metadata(row, group)

    parameter, _created = await cp_repo.upsert_by_code(
        parameter_code=code,
        values={
            "canonical_name": name,
            "default_unit": _clean(row.get("unit")) or None,
            "category": _clean(row.get("category")) or None,
            "active_phase1": active,
            "analysis_level": match.analysis_level if match else PASSIVE_LEVEL,
            "metadata_json": metadata,
        },
    )
    await cp_repo.flush()  # ensure parameter.id is populated

    stats.parameters += 1
    if active:
        stats.active += 1
    else:
        stats.passive += 1

    # --- Aliases (locally de-duplicated by normalized key) --------------
    alias_specs: list[tuple[str, float, str]] = [(name, 1.0, "csv_canonical")]
    if match:
        alias_specs.extend(
            (alias, 0.9, "phase1_seed") for alias in match.aliases
        )

    seen_norm: set[str] = set()
    for alias_text, confidence, source in alias_specs:
        norm = normalize_alias(alias_text)
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)
        created_alias = await alias_repo.add_unique(
            canonical_parameter_id=parameter.id,
            alias=alias_text,
            confidence=confidence,
            source=source,
        )
        if created_alias is not None:
            stats.aliases += 1

    # --- Reference ranges (rebuilt for idempotent re-import) ------------
    await rr_repo.delete_for_parameter(parameter.id)

    is_qualitative = bool(metadata["is_qualitative"])
    no_upper_limit = bool(metadata["no_upper_limit"])
    unit = _clean(row.get("unit")) or None
    range_source = _clean(row.get("reference_source")) or _settings.csv_import_default_source

    if not is_qualitative:
        for band in DEMOGRAPHIC_BANDS:
            low = _parse_decimal(row.get(band.min_column))
            high = _parse_decimal(row.get(band.max_column))
            if low is None and high is None:
                continue
            if no_upper_limit:
                high = None
            rr_repo.add(
                ReferenceRange(
                    parameter_id=parameter.id,
                    sex=band.sex,
                    age_min=band.age_min,
                    age_max=band.age_max,
                    pregnancy_status=band.pregnancy_status,
                    reference_min=low,
                    reference_max=high,
                    unit=unit,
                    source=range_source,
                    metadata_json={
                        "band": band.key,
                        "no_upper_limit": no_upper_limit,
                    },
                )
            )
            stats.ranges += 1

    await rr_repo.flush()


async def run_import(csv_path: Path) -> ImportStats:
    rows = _load_rows(csv_path)
    stats = ImportStats()
    used_codes: set[str] = set()

    async with AsyncSessionFactory() as session:
        cp_repo = ClinicalParameterRepository(session)
        alias_repo = ParameterAliasRepository(session)
        rr_repo = ReferenceRangeRepository(session)
        try:
            for row in rows:
                await _import_row(
                    row,
                    used_codes=used_codes,
                    cp_repo=cp_repo,
                    alias_repo=alias_repo,
                    rr_repo=rr_repo,
                    stats=stats,
                )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return stats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import lab reference parameters from CSV.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="Path to the reference CSV (source of truth).",
    )
    return parser.parse_args()


async def _main_async(csv_path: Path) -> None:
    if not csv_path.exists():
        raise FileNotFoundError(f"Reference CSV not found: {csv_path}")
    stats = await run_import(csv_path)
    # Summary counts only — CSV contents are never printed.
    print(
        "Import complete: "
        f"{stats.parameters} parameters "
        f"({stats.active} active / {stats.passive} passive), "
        f"{stats.aliases} aliases, {stats.ranges} reference ranges."
    )
    await engine.dispose()


def main() -> None:
    args = _parse_args()
    asyncio.run(_main_async(args.csv))


if __name__ == "__main__":
    main()
