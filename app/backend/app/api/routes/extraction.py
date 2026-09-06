"""Lab report extraction routes.

The extraction-only endpoint keeps the existing Claude extractor. The analysis
endpoint now routes uploaded PDF/image content through the same Astra/OpenAI +
native C++ pipeline used by the direct laboratory upload path, so JPG uploads no
longer fall back to the legacy extraction pipeline.
"""

from __future__ import annotations

import mimetypes
import uuid
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import ClaudeLabExtractionServiceDep, SessionDep
from app.api.routes import lab_pdf_direct_upload
from app.core.config import get_settings
from app.domain.claude_lab_extraction_service import SUPPORTED_CONTENT_TYPES
from app.infrastructure.runtime_resilience import (
    DependencyBusyError,
    DependencyCircuitOpenError,
    DependencyGuardError,
    DependencyTimeoutError,
)
from app.schemas.extraction import (
    ExtractedLabValue,
    ExtractionAndAnalysisResult,
    LabExtractionResult,
)

router = APIRouter(prefix="/extraction", tags=["extraction"])


def _resolve_content_type(file: UploadFile) -> str | None:
    content_type = (file.content_type or "").lower().strip() or None
    if content_type in SUPPORTED_CONTENT_TYPES:
        return content_type
    guessed, _ = mimetypes.guess_type(file.filename or "")
    return guessed if guessed in SUPPORTED_CONTENT_TYPES else content_type


async def _read_supported_upload(file: UploadFile) -> tuple[bytes, str]:
    content_type = _resolve_content_type(file)
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Laboratuvar analizi için PDF, JPG/JPEG, PNG veya WEBP yükleyin.",
        )

    max_upload_bytes = get_settings().lab_extraction_max_bytes
    data = await file.read(max_upload_bytes + 1)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Boş laboratuvar dosyası analiz edilemez.",
        )
    if len(data) > max_upload_bytes:
        max_megabytes = max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Laboratuvar dosyası {max_megabytes} MB sınırını aşıyor.",
        )
    return data, content_type


def _dependency_http_error(exc: DependencyGuardError) -> HTTPException:
    if isinstance(exc, DependencyTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Laboratuvar AI çıkarımı zaman aşımına uğradı. Dosya daha sonra yeniden denenebilir veya sonuçlar manuel girilebilir.",
        )
    if isinstance(exc, (DependencyBusyError, DependencyCircuitOpenError)):
        detail = "Laboratuvar AI çıkarımı geçici olarak yoğun veya koruma devresi açık. Kısa süre sonra yeniden deneyin."
    else:
        detail = "Laboratuvar AI çıkarım servisi geçici olarak kullanılamıyor."
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


@router.post("/lab-report", response_model=LabExtractionResult)
async def extract_lab_report(
    service: ClaudeLabExtractionServiceDep,
    file: UploadFile = File(...),
) -> LabExtractionResult:
    data, content_type = await _read_supported_upload(file)
    try:
        return await service.extract_from_bytes(data, file.filename, content_type)
    except DependencyGuardError as exc:
        raise _dependency_http_error(exc) from None
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
    session: SessionDep,
    patient_id: uuid.UUID = Form(...),
    uploaded_by_user_id: uuid.UUID | None = Form(default=None),
    report_date: date | None = Form(default=None),
    file: UploadFile = File(...),
) -> ExtractionAndAnalysisResult:
    """Analyze a lab document with Astra/OpenAI and the native C++ lab core.

    `patient_id`, `uploaded_by_user_id`, and `report_date` remain in the request
    contract for backwards compatibility with the existing frontend. The direct
    pipeline creates the analysis result first; the existing archive-save flow then
    associates the generated report with the selected patient record.
    """
    del patient_id, uploaded_by_user_id, report_date

    data, content_type = await _read_supported_upload(file)
    file_name = file.filename or "laboratuvar-dosyasi"

    analysis = await lab_pdf_direct_upload._analyze_prepared_documents(
        session=session,
        documents=[(data, content_type, file_name)],
    )

    extracted_values = [
        ExtractedLabValue(
            raw_parameter_name=item.raw_parameter_name,
            raw_value=str(item.normalized_value) if item.normalized_value is not None else None,
            normalized_value=item.normalized_value,
            unit=item.unit,
            extracted_reference_min=item.reference_min,
            extracted_reference_max=item.reference_max,
            extracted_unit=item.unit,
            measured_at=item.measured_at,
            needs_review=item.needs_review,
            extraction_note=item.reason,
        )
        for item in analysis.results
    ]

    extraction = LabExtractionResult(
        values=extracted_values,
        overall_needs_review=any(item.needs_review for item in analysis.results),
        extraction_confidence=(
            min((item.alias_confidence for item in analysis.results), default=0.0)
            if analysis.results
            else None
        ),
        source_file_name=file_name,
        warnings=[],
    )

    return ExtractionAndAnalysisResult(extraction=extraction, analysis=analysis)
