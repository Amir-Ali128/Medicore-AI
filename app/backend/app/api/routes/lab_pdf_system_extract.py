"""System-backed laboratory PDF extraction.

This route keeps the existing deterministic PDF parser as the first pass, then
looks up the laboratory parameter dictionary stored in MediCore and attempts to
extract any additional tests present in the PDF. This prevents the upload flow
from being limited to the hard-coded MVP test list.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import text as sql_text

from app.api.dependencies import AnalysisPipelineDep
from app.api.routes import lab_analysis
from app.infrastructure.database.session import AsyncSessionFactory
from app.schemas.lab_analysis import AnalysisPipelineResult, MockLabReportInput

router = APIRouter(prefix="/lab-analysis", tags=["lab-analysis"])


def _name_key(value: str) -> str:
    normalized = lab_analysis._normalize_text(value).upper()
    return re.sub(r"[^A-Z0-9ÇĞİÖŞÜ]+", "", normalized)


async def _load_system_parameter_catalog() -> list[dict[str, Any]]:
    """Load canonical tests and aliases from MediCore's parameter dictionary.

    The database is the source of truth. If an older deployment does not yet
    contain the alias table, the caller safely falls back to the existing static
    parser instead of failing the upload.
    """
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


def _parse_system_values(
    text: str,
    catalog: list[dict[str, Any]],
    already_parsed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_text = lab_analysis._normalize_text(text)
    lines = [
        line.strip()
        for line in normalized_text.splitlines()
        if line.strip() and not lab_analysis._is_noise_line(line)
    ]

    matched_keys: set[str] = set()
    for parsed in already_parsed:
        raw_name = str(parsed.get("raw_parameter_name") or "")
        config = lab_analysis.LAB_PARAMETER_ALIASES.get(raw_name)
        matched_keys.add(_name_key(raw_name))
        if config:
            matched_keys.update(_name_key(alias) for alias in config.get("aliases", []))

    extra_values: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    for item in catalog:
        parameter_code = str(item["parameter_code"])
        canonical_name = str(item["canonical_name"])
        aliases = [
            canonical_name,
            parameter_code,
            *[str(alias) for alias in item.get("aliases", []) if str(alias).strip()],
        ]

        candidate_keys = {_name_key(value) for value in aliases if value}
        if candidate_keys & matched_keys:
            continue
        if parameter_code in seen_codes:
            continue

        # Prefer longer aliases so a specific test name wins over a short token.
        unique_aliases = sorted(set(aliases), key=len, reverse=True)
        parsed = lab_analysis._find_parameter_value_in_lines(
            raw_parameter_name=parameter_code,
            aliases=unique_aliases,
            default_unit=str(item.get("default_unit") or ""),
            lines=lines,
        )
        if parsed is None:
            continue

        extra_values.append(parsed)
        seen_codes.add(parameter_code)
        matched_keys.update(candidate_keys)

    return extra_values


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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported for this upload flow.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF is empty.",
        )
    if len(file_bytes) > lab_analysis._MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded PDF is too large. Maximum size is 10 MB.",
        )

    extracted_text = lab_analysis._extract_text_from_pdf(file_bytes)
    if not extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No selectable text could be extracted from this PDF. Scanned/image PDFs need OCR.",
        )

    patient_metadata = lab_analysis._parse_patient_metadata_from_text(extracted_text)

    # Ensure the reference dictionary is ready before reading the system catalog.
    await lab_analysis._ensure_demo_patient_and_user()

    static_values = lab_analysis._parse_lab_values_from_text(extracted_text)
    system_catalog = await _load_system_parameter_catalog()
    system_values = _parse_system_values(extracted_text, system_catalog, static_values)
    values = [*static_values, *system_values]

    if not values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PDF içinde sistem sözlüğüyle eşleşen laboratuvar sonucu bulunamadı.",
        )

    payload = MockLabReportInput(
        patient_id=lab_analysis.DEMO_PATIENT_ID,
        uploaded_by_user_id=lab_analysis.DEMO_UPLOADED_BY_USER_ID,
        file_name=file.filename,
        report_date=date.today(),
        values=values,
    )

    try:
        result = await pipeline.run(payload)
        return result.model_copy(update={"patient": patient_metadata})
    except ValueError as exc:
        lab_analysis._raise_pipeline_error(exc)
