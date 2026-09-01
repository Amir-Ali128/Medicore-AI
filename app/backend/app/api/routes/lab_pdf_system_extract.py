"""System-backed laboratory PDF extraction.

The upload flow is intentionally PDF-first: every blood-test row that can be
read from the report is preserved, then MediCore's parameter dictionary is used
when possible. Rows not yet present in the dictionary receive a stable PDF
parameter entry so an extracted reference range can still be classified
deterministically instead of being dropped.

Rules:
- Prefer the reference interval printed in the PDF.
- Support two-sided ranges and one-sided limits (< / >).
- Keep blood tests only; urine/stool rows are not mixed into blood counts.
- Numeric rows become NORMAL / LOW / HIGH when a usable reference is present.
- Exact qualitative "Negatif" rows with a negative reference are stored as a
  deterministic normal result (0 within 0..0).
- A result with no report reference may fall back to an existing MediCore
  reference range; if none exists it remains physician-review rather than being
  guessed.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import text as sql_text

from app.api.dependencies import AnalysisPipelineDep
from app.api.routes import lab_analysis
from app.infrastructure.database.session import AsyncSessionFactory
from app.schemas.lab_analysis import AnalysisPipelineResult, MockLabReportInput

router = APIRouter(prefix="/lab-analysis", tags=["lab-analysis"])

# Open-ended report limits are represented with a very distant opposite bound
# so the existing deterministic RuleEngine can classify them. These constants
# are presentation sentinels, not clinical reference values.
_OPEN_LOW = -1_000_000_000.0
_OPEN_HIGH = 1_000_000_000.0

_NUMERIC_ROW_RE = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<value>[<>]?\s*[-+]?\d+(?:\.\d+)?)\s+"
    r"(?P<unit>---|[%A-Za-z0-9^./]+(?:/[A-Za-z0-9.^]+)*)\s+"
    r"(?P<reference>(?:[<>]\s*)?[-+]?\d+(?:\.\d+)?(?:\s*-\s*[-+]?\d+(?:\.\d+)?)?)$",
    flags=re.IGNORECASE,
)
_NUMERIC_NO_REFERENCE_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<value>[<>]?\s*[-+]?\d+(?:\.\d+)?)\s+---$",
    flags=re.IGNORECASE,
)
_NEGATIVE_ROW_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<value><\s*1\s*:\s*10\s+Negatif|Negatif(?:\s*\(-\))?)\s+(?P<unit>Titre|---)$",
    flags=re.IGNORECASE,
)

_NON_BLOOD_NAME_MARKERS = (
    "GAITA",
    "PARAZIT",
    "ROTAVIRUS",
    "CLOSTRIDIUM",
    "IDRAR",
    "URINE",
)

_IGNORE_LINE_MARKERS = (
    "T.C.SAGLIK BAKANLIGI",
    "SAGLIK BILGI SISTEMLERI",
    "SAGLIK TESISI",
    "TARIH TAHLIL",
    "SONUC BIRIMI",
    "REFERANS DEGERI",
    "ENABIZ.GOV.TR",
    "TAM KAN SAYIMI",
    "KOLESTEROL (SERUM/PLAZMA)",
    "KREATININ (SERUM/PLAZMA)",
    "ANTI ENDOMISYUM ANTIKOR",
    "CALISILAN HUCRE/DOKU",
)


def _name_key(value: str) -> str:
    normalized = lab_analysis._normalize_text(value).upper()
    return re.sub(r"[^A-Z0-9]+", "", normalized)


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", lab_analysis._normalize_text(value)).strip()


def _parse_number(value: str) -> float | None:
    cleaned = value.replace("<", "").replace(">", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_reference(value: str | None) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    reference = value.strip()
    if reference.startswith("<"):
        number = _parse_number(reference)
        return (_OPEN_LOW, number) if number is not None else (None, None)
    if reference.startswith(">"):
        number = _parse_number(reference)
        return (number, _OPEN_HIGH) if number is not None else (None, None)

    range_match = re.fullmatch(
        r"\s*([-+]?\d+(?:\.\d+)?)\s*-\s*([-+]?\d+(?:\.\d+)?)\s*",
        reference,
    )
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        return (low, high) if low <= high else (None, None)

    number = _parse_number(reference)
    if number is not None:
        # A lone reference value is not enough to infer direction safely.
        return None, None
    return None, None


def _extract_report_date(text: str) -> date:
    for match in re.finditer(r"\b(\d{2}\.\d{2}\.\d{4})\b", text):
        try:
            return datetime.strptime(match.group(1), "%d.%m.%Y").date()
        except ValueError:
            continue
    return date.today()


def _looks_like_ignored_line(line: str) -> bool:
    upper = line.upper()
    if not line:
        return True
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", line):
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}", line):
        return True
    if line.startswith("0 850 ") or line.startswith("Sayfa "):
        return True
    return any(marker in upper for marker in _IGNORE_LINE_MARKERS)


def _is_non_blood_test(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in _NON_BLOOD_NAME_MARKERS)


def _row_from_numeric_match(match: re.Match[str], report_date: date) -> dict[str, Any] | None:
    raw_name = match.group("name").strip(" :-")
    if not raw_name or _is_non_blood_test(raw_name):
        return None

    value = _parse_number(match.group("value"))
    if value is None:
        return None
    unit = match.group("unit").strip()
    if unit == "---":
        unit = ""
    low, high = _parse_reference(match.groupdict().get("reference"))
    return {
        "display_name": raw_name,
        "raw_value": match.group("value").strip(),
        "normalized_value": value,
        "unit": unit,
        "extracted_reference_min": low,
        "extracted_reference_max": high,
        "extracted_unit": unit,
        "measured_at": report_date.isoformat(),
        "qualitative_normal": False,
    }


def _row_from_negative_match(match: re.Match[str], report_date: date) -> dict[str, Any] | None:
    raw_name = match.group("name").strip(" :-")
    if not raw_name or _is_non_blood_test(raw_name):
        return None
    unit = match.group("unit").strip()
    if unit == "---":
        unit = ""
    return {
        "display_name": raw_name,
        "raw_value": match.group("value").strip(),
        "normalized_value": 0.0,
        "unit": unit,
        "extracted_reference_min": 0.0,
        "extracted_reference_max": 0.0,
        "extracted_unit": unit,
        "measured_at": report_date.isoformat(),
        "qualitative_normal": True,
    }


def _parse_all_blood_rows(text: str, report_date: date) -> list[dict[str, Any]]:
    """Parse all blood rows in a tabular PDF, including wrapped test names."""
    normalized_lines = [_clean_line(line) for line in text.splitlines()]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    pending_name_parts: list[str] = []
    in_urine_section = False

    for line in normalized_lines:
        if not line:
            continue
        upper = line.upper()

        # e-Nabız and similar exports can place urine in the same PDF. The page
        # footer ends that table; later blood antibody pages are allowed again.
        if "TAM IDRAR ANALIZI" in upper or "URINALYSIS" in upper:
            in_urine_section = True
            pending_name_parts.clear()
            continue
        if line.startswith("Sayfa "):
            in_urine_section = False
            pending_name_parts.clear()
            continue
        if in_urine_section:
            continue

        match = _NUMERIC_ROW_RE.match(line)
        if match:
            row = _row_from_numeric_match(match, report_date)
            pending_name_parts.clear()
            if row:
                key = _name_key(row["display_name"])
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        no_reference = _NUMERIC_NO_REFERENCE_RE.match(line)
        if no_reference:
            row = _row_from_numeric_match(no_reference, report_date)
            pending_name_parts.clear()
            if row:
                key = _name_key(row["display_name"])
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        negative = _NEGATIVE_ROW_RE.match(line)
        if negative:
            row = _row_from_negative_match(negative, report_date)
            pending_name_parts.clear()
            if row:
                key = _name_key(row["display_name"])
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
            continue

        # Wrapped name: e.g. "Doymamış Demir Bağlama" / "Kapasitesi" /
        # "413 ug/dL 75 - 360". Join at most two name lines to avoid headers.
        if re.match(r"^[<>]?\s*[-+]?\d+(?:\.\d+)?\s+", line) and pending_name_parts:
            combined = " ".join([*pending_name_parts[-2:], line])
            wrapped = _NUMERIC_ROW_RE.match(combined)
            pending_name_parts.clear()
            if wrapped:
                row = _row_from_numeric_match(wrapped, report_date)
                if row:
                    key = _name_key(row["display_name"])
                    if key and key not in seen:
                        seen.add(key)
                        rows.append(row)
            continue

        if _looks_like_ignored_line(line) or _is_non_blood_test(line):
            pending_name_parts.clear()
            continue

        # Only alphabetic heading fragments are candidates for wrapped names.
        if re.search(r"[A-Za-z]", line) and not re.search(r"\d", line):
            pending_name_parts.append(line)
            pending_name_parts[:] = pending_name_parts[-2:]
        else:
            pending_name_parts.clear()

    return rows


async def _load_system_parameter_catalog() -> list[dict[str, Any]]:
    try:
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                sql_text(
                    """
                    SELECT
                        cp.parameter_code,
                        cp.canonical_name,
                        COALESCE(cp.default_unit, '') AS default_unit,
                        pa.alias
                    FROM clinical_parameters AS cp
                    LEFT JOIN parameter_aliases AS pa
                      ON pa.canonical_parameter_id = cp.id
                    ORDER BY cp.canonical_name, pa.alias
                    """
                )
            )
            rows = result.mappings().all()
    except Exception:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("parameter_code") or "").strip()
        canonical = str(row.get("canonical_name") or "").strip()
        if not code or not canonical:
            continue
        item = grouped.setdefault(
            code,
            {
                "parameter_code": code,
                "canonical_name": canonical,
                "default_unit": str(row.get("default_unit") or "").strip(),
                "aliases": [],
            },
        )
        alias = str(row.get("alias") or "").strip()
        if alias:
            item["aliases"].append(alias)
    return list(grouped.values())


def _catalog_index(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in catalog:
        names = [
            str(item.get("parameter_code") or ""),
            str(item.get("canonical_name") or ""),
            *[str(alias) for alias in item.get("aliases", [])],
        ]
        for name in names:
            key = _name_key(name)
            if key:
                index.setdefault(key, item)
    return index


def _dynamic_parameter_code(display_name: str) -> str:
    digest = hashlib.sha1(_name_key(display_name).encode("utf-8")).hexdigest()[:20].upper()
    return f"PDF_{digest}"


async def _ensure_dynamic_parameters(rows: list[dict[str, Any]]) -> None:
    dynamic_rows = [row for row in rows if row.get("dynamic") is True]
    if not dynamic_rows:
        return

    async with AsyncSessionFactory() as session:
        for row in dynamic_rows:
            code = str(row["parameter_code"])
            canonical = str(row["display_name"])[:255]
            default_unit = str(row.get("unit") or "")[:64]
            existing = (
                await session.execute(
                    sql_text("SELECT id FROM clinical_parameters WHERE parameter_code = :code LIMIT 1"),
                    {"code": code},
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue

            await session.execute(
                sql_text(
                    """
                    INSERT INTO clinical_parameters (
                        id, parameter_code, canonical_name, default_unit, category,
                        active_phase1, analysis_level, metadata_json, created_at, updated_at
                    )
                    VALUES (
                        :id, :code, :canonical, :default_unit, 'pdf_import', true,
                        (
                            SELECT enumlabel::analysis_level
                            FROM pg_enum
                            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                            WHERE pg_type.typname = 'analysis_level'
                              AND enumlabel <> 'L0'
                            ORDER BY enumsortorder
                            LIMIT 1
                        ),
                        '{"source":"pdf_report_dynamic_parameter","report_reference_preferred":true}'::jsonb,
                        NOW(), NOW()
                    )
                    ON CONFLICT (parameter_code) DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"medicore-pdf:{code}")),
                    "code": code,
                    "canonical": canonical,
                    "default_unit": default_unit,
                },
            )
        await session.commit()


def _map_rows_to_parameters(
    rows: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index = _catalog_index(catalog)
    mapped: list[dict[str, Any]] = []

    for row in rows:
        item = index.get(_name_key(str(row["display_name"])))
        if item is not None:
            parameter_code = str(item["parameter_code"])
            dynamic = False
        else:
            parameter_code = _dynamic_parameter_code(str(row["display_name"]))
            dynamic = True

        mapped.append(
            {
                **row,
                "parameter_code": parameter_code,
                "dynamic": dynamic,
            }
        )
    return mapped


def _to_pipeline_values(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in rows:
        values.append(
            {
                # Passing the stable parameter code guarantees deterministic
                # AliasEngine resolution; canonical display name stays in DB.
                "raw_parameter_name": row["parameter_code"],
                "raw_value": row["raw_value"],
                "normalized_value": row["normalized_value"],
                "unit": row["unit"] or None,
                "extracted_reference_min": row["extracted_reference_min"],
                "extracted_reference_max": row["extracted_reference_max"],
                "extracted_unit": row["unit"] or None,
                "measured_at": row["measured_at"],
            }
        )
    return values


@router.post(
    "/upload",
    response_model=AnalysisPipelineResult,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_uploaded_pdf_report_with_system_catalog(
    pipeline: AnalysisPipelineDep,
    file: UploadFile = File(...),
) -> AnalysisPipelineResult:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported for this upload flow.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
    if len(file_bytes) > lab_analysis._MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded PDF is too large. Maximum size is 10 MB.",
        )

    extracted_text = lab_analysis._extract_text_from_pdf(file_bytes)
    if not extracted_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No selectable text could be extracted from this PDF. Scanned/image PDFs need OCR.",
        )

    patient_metadata = lab_analysis._parse_patient_metadata_from_text(extracted_text)
    report_date = _extract_report_date(extracted_text)

    # Prepare the normal MediCore dictionary first, then add only truly unseen
    # PDF tests as stable dynamic parameters.
    await lab_analysis._ensure_demo_patient_and_user()
    catalog = await _load_system_parameter_catalog()
    parsed_rows = _parse_all_blood_rows(extracted_text, report_date)
    mapped_rows = _map_rows_to_parameters(parsed_rows, catalog)
    await _ensure_dynamic_parameters(mapped_rows)
    values = _to_pipeline_values(mapped_rows)

    if not values:
        raise HTTPException(
            status_code=400,
            detail="PDF içinde sınıflandırılabilir kan tahlili sonucu bulunamadı.",
        )

    payload = MockLabReportInput(
        patient_id=lab_analysis.DEMO_PATIENT_ID,
        uploaded_by_user_id=lab_analysis.DEMO_UPLOADED_BY_USER_ID,
        file_name=file.filename,
        report_date=report_date,
        values=values,
    )

    try:
        result = await pipeline.run(payload)
        return result.model_copy(update={"patient": patient_metadata})
    except ValueError as exc:
        lab_analysis._raise_pipeline_error(exc)
