"""Simplified physician-facing CDSS endpoint.

Input:
- laboratory PDF/image
- structured clinical context JSON
- radiology/imaging report text or PDF/TXT

Output:
- structured lab extraction
- integrated doctor-style CDSS report for physician review
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import mimetypes

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from pypdf import PdfReader

from app.api.dependencies import (
    ClaudeCDSSReportServiceDep,
    ClaudeLabExtractionServiceDep,
)
from app.core.config import get_settings
from app.domain.claude_lab_extraction_service import SUPPORTED_CONTENT_TYPES
from app.infrastructure.runtime_resilience import (
    DependencyBusyError,
    DependencyCircuitOpenError,
    DependencyGuardError,
    DependencyTimeoutError,
)
from app.schemas.cdss_report import CDSSReportGenerationResult, ClinicalContext

router = APIRouter(prefix="/cdss", tags=["cdss"])

_MAX_IMAGING_TEXT_CHARS = 30_000


def _resolve_content_type(file: UploadFile) -> str | None:
    content_type = (file.content_type or "").lower().strip() or None
    if content_type:
        return content_type
    guessed, _ = mimetypes.guess_type(file.filename or "")
    return guessed


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    data = await file.read(max_bytes + 1)

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{file.filename or 'Yüklenen dosya'} boş.",
        )

    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Yüklenen dosya izin verilen boyut sınırını aşıyor.",
        )

    return data


def _extract_imaging_text(
    data: bytes,
    content_type: str | None,
) -> str:
    if content_type == "text/plain":
        return data.decode("utf-8", errors="replace").strip()

    if content_type == "application/pdf":
        try:
            reader = PdfReader(BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Görüntüleme raporu PDF dosyası okunamadı.",
            ) from exc

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Görüntüleme raporu PDF dosyasında seçilebilir metin bulunamadı. "
                    "Rapor metnini manuel olarak girin."
                ),
            )

        return text

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Görüntüleme raporu için PDF, TXT veya metin kullanın.",
    )


def _dependency_http_error(exc: DependencyGuardError) -> HTTPException:
    if isinstance(exc, DependencyTimeoutError):
        return HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="CDSS yapay zeka değerlendirmesi zaman aşımına uğradı.",
        )

    if isinstance(exc, (DependencyBusyError, DependencyCircuitOpenError)):
        detail = (
            "CDSS yapay zeka servisi geçici olarak yoğun veya koruma devresi açık. "
            "Kısa süre sonra yeniden deneyin."
        )
    else:
        detail = "CDSS yapay zeka servisi geçici olarak kullanılamıyor."

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


@router.post(
    "/report",
    response_model=CDSSReportGenerationResult,
    status_code=status.HTTP_201_CREATED,
)
async def generate_cdss_report(
    extraction_service: ClaudeLabExtractionServiceDep,
    cdss_service: ClaudeCDSSReportServiceDep,
    clinical_data: str = Form(...),
    imaging_report_text: str | None = Form(default=None),
    lab_report: UploadFile = File(...),
    imaging_report_file: UploadFile | None = File(default=None),
) -> CDSSReportGenerationResult:
    try:
        clinical_context = ClinicalContext.model_validate_json(clinical_data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "clinical_data geçerli ClinicalContext JSON değil.",
                "errors": exc.errors(),
            },
        ) from None

    settings = get_settings()

    lab_content_type = _resolve_content_type(lab_report)
    if lab_content_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kan tetkiki için PDF, JPG/JPEG, PNG veya WEBP yükleyin.",
        )

    lab_bytes = await _read_limited(
        lab_report,
        settings.lab_extraction_max_bytes,
    )

    try:
        lab_extraction = await extraction_service.extract_from_bytes(
            lab_bytes,
            lab_report.filename,
            lab_content_type,
        )
    except DependencyGuardError as exc:
        raise _dependency_http_error(exc) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None

    final_imaging_text = (imaging_report_text or "").strip()

    if imaging_report_file is not None:
        imaging_bytes = await _read_limited(
            imaging_report_file,
            settings.radiology_image_max_bytes,
        )
        file_text = _extract_imaging_text(
            imaging_bytes,
            _resolve_content_type(imaging_report_file),
        )
        final_imaging_text = (
            f"{final_imaging_text}\n\n{file_text}".strip()
            if final_imaging_text
            else file_text
        )

    if not final_imaging_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "imaging_report_text veya imaging_report_file alanlarından "
                "en az biri zorunludur."
            ),
        )

    if len(final_imaging_text) > _MAX_IMAGING_TEXT_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Görüntüleme raporu metni çok uzun.",
        )

    try:
        report = await cdss_service.generate_report(
            clinical_context=clinical_context,
            lab_extraction=lab_extraction,
            imaging_report_text=final_imaging_text,
        )
    except DependencyGuardError as exc:
        raise _dependency_http_error(exc) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from None

    warnings = list(lab_extraction.warnings)

    if lab_extraction.overall_needs_review:
        warnings.append(
            "Bazı laboratuvar değerleri klinik kullanım öncesinde çıkarım kontrolü gerektiriyor."
        )

    return CDSSReportGenerationResult(
        generated_at=datetime.now(timezone.utc),
        clinical_context=clinical_context,
        lab_extraction=lab_extraction,
        imaging_report_text=final_imaging_text,
        report=report,
        warnings=warnings,
    )
