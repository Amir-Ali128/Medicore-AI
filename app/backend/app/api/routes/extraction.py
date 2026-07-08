"""Lab report extraction routes.

Extraction only: Claude reads structured lab values off an uploaded image/PDF.
No diagnosis, no interpretation, no treatment advice. The optional analyze
endpoint feeds the extracted values into the existing deterministic pipeline.
"""

from __future__ import annotations

import mimetypes
import uuid
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import (
    AnalysisPipelineDep,
    ClaudeLabExtractionServiceDep,
)
from app.domain.claude_lab_extraction_service import (
    SUPPORTED_CONTENT_TYPES,
)
from app.schemas.extraction import (
    ExtractionAndAnalysisResult,
    LabExtractionResult,
)
from app.schemas.lab_analysis import MockLabReportInput, RawLabValue

router = APIRouter(prefix="/extraction", tags=["extraction"])

_PATIENT_NOT_FOUND = "Patient not found."


def _resolve_content_type(file: UploadFile) -> str | None:
    content_type = (file.content_type or "").lower() or None
    if content_type in SUPPORTED_CONTENT_TYPES:
        return content_type
    guessed, _ = mimetypes.guess_type(file.filename or "")
    return guessed or content_type


@router.post("/lab-report", response_model=LabExtractionResult)
async def extract_lab_report(
    service: ClaudeLabExtractionServiceDep,
    file: UploadFile = File(...),
) -> LabExtractionResult:
    data = await file.read()
    content_type = _resolve_content_type(file)
    try:
        return await service.extract_from_bytes(data, file.filename, content_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None


@router.post(
    "/lab-report/analyze",
    response_model=ExtractionAndAnalysisResult,
    status_code=status.HTTP_201_CREATED,
)
async def extract_and_analyze_lab_report(
    service: ClaudeLabExtractionServiceDep,
    pipeline: AnalysisPipelineDep,
    patient_id: uuid.UUID = Form(...),
    uploaded_by_user_id: uuid.UUID | None = Form(default=None),
    report_date: date | None = Form(default=None),
    file: UploadFile = File(...),
) -> ExtractionAndAnalysisResult:
    data = await file.read()
    content_type = _resolve_content_type(file)

    try:
        extraction = await service.extract_from_bytes(data, file.filename, content_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None

    raw_values = [
        RawLabValue(
            raw_parameter_name=item.raw_parameter_name or "",
            raw_value=item.raw_value,
            normalized_value=item.normalized_value,
            unit=item.unit,
            extracted_reference_min=item.extracted_reference_min,
            extracted_reference_max=item.extracted_reference_max,
            extracted_unit=item.extracted_unit,
            measured_at=item.measured_at,
        )
        for item in extraction.values
    ]

    payload = MockLabReportInput(
        patient_id=patient_id,
        uploaded_by_user_id=uploaded_by_user_id,
        file_name=file.filename,
        report_date=report_date,
        values=raw_values,
    )

    try:
        analysis = await pipeline.run(payload)
    except ValueError as exc:
        message = str(exc)
        if message == _PATIENT_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=message
            ) from None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=message
        ) from None

    return ExtractionAndAnalysisResult(extraction=extraction, analysis=analysis)
