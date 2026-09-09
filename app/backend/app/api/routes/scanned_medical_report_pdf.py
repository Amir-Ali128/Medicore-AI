"""Upload endpoint for image-only/scanned medical report PDFs.

Text PDFs continue to use the lightweight parser. This route is selected by the
frontend for PDFs and uses multimodal extraction only when the source needs it,
then hands the de-identified text to the normal universal report pipeline.
"""

from __future__ import annotations

import io
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pypdf import PdfReader

from app.api.dependencies import SessionDep
from app.api.routes import radiology_reports
from app.api.routes.auth import get_current_active_user
from app.domain.scanned_medical_report_pdf_ai import (
    ScannedMedicalReportExtractionError,
    extract_scanned_medical_report_pdf,
)
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.infrastructure.database.models.user import User
from app.schemas.radiology_report import RadiologyReportCreate, RadiologyReportResponse

router = APIRouter(prefix="/radiology-reports", tags=["medical-report-pdf"])

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _looks_like_pdf(filename: str, content_type: str | None) -> bool:
    return (
        Path(filename).suffix.lower() == ".pdf"
        or (content_type or "").split(";", 1)[0].strip().lower() == "application/pdf"
    )


def _native_pdf_text(content: bytes) -> str | None:
    """Return embedded text when present; image-only PDFs return None."""
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="PDF dosyası okunamadı.") from exc

    text = "\n".join(
        part
        for part in ((page.extract_text() or "").strip() for page in reader.pages)
        if part
    ).strip()
    return text if len(text) >= 10 else None


async def _save_unanalyzed_fallback(
    *,
    patient_id: uuid.UUID,
    report_date: date | None,
    modality: str | None,
    body_part: str | None,
    filename: str,
    content: bytes,
    session: SessionDep,
    current_user: User,
    reason: str,
) -> RadiologyReport:
    report = await radiology_reports._persist_binary_file(
        patient_id=patient_id,
        report_date=report_date,
        modality=modality,
        body_part=body_part,
        filename=filename,
        content_type="application/pdf",
        content=content,
        session=session,
        current_user=current_user,
    )
    metadata = dict(report.metadata_json or {})
    metadata.update(
        {
            "scanned_pdf_extraction_attempted": True,
            "scanned_pdf_extraction_status": "unavailable",
            "scanned_pdf_extraction_error": reason[:800],
            "analysis_available": False,
            "physician_review_required": True,
        }
    )
    report.metadata_json = metadata
    report.summary = (
        "PDF arşivlendi ancak taranmış belge metni otomatik çıkarılamadı; "
        "klinik değerlendirme için yeniden denenmesi veya hekim incelemesi gerekir."
    )
    await session.commit()
    await session.refresh(report)
    return report


@router.post(
    "/scanned-pdf",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_medical_report_pdf(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
    patient_id: uuid.UUID = Form(...),
    report_date: date | None = Form(None),
    modality: str | None = Form(None),
    body_part: str | None = Form(None),
) -> RadiologyReport:
    filename = (file.filename or "medical-report.pdf").strip() or "medical-report.pdf"
    if not _looks_like_pdf(filename, file.content_type):
        raise HTTPException(status_code=400, detail="Bu uç nokta yalnızca PDF raporları içindir.")

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Boş PDF yüklenemez.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="PDF 15 MB sınırını aşıyor.")

    # Cheap path first: text-based PDFs do not need multimodal extraction.
    embedded_text = _native_pdf_text(content)
    extraction_metadata: dict[str, object] = {
        "content_type": "application/pdf",
        "upload_size_bytes": len(content),
        "original_file_stored": True,
        "physician_review_required": True,
    }
    source_type = "pdf_upload"
    report_text = embedded_text

    if report_text is None:
        try:
            extraction = await extract_scanned_medical_report_pdf(
                content=content,
                file_name=filename,
            )
        except ScannedMedicalReportExtractionError as exc:
            return await _save_unanalyzed_fallback(
                patient_id=patient_id,
                report_date=report_date,
                modality=modality,
                body_part=body_part,
                filename=filename,
                content=content,
                session=session,
                current_user=current_user,
                reason=str(exc),
            )

        if extraction is None:
            return await _save_unanalyzed_fallback(
                patient_id=patient_id,
                report_date=report_date,
                modality=modality,
                body_part=body_part,
                filename=filename,
                content=content,
                session=session,
                current_user=current_user,
                reason="multimodal_pdf_extractor_not_configured",
            )

        report_text = extraction.deidentified_text
        source_type = "scanned_pdf_ai_extract"
        extraction_metadata.update(
            {
                "scanned_pdf_extraction_attempted": True,
                "scanned_pdf_extraction_status": "completed",
                "scanned_pdf_extraction_model": extraction.model,
                "scanned_pdf_document_type": extraction.document_type,
                "scanned_pdf_extraction_confidence": extraction.confidence,
                "scanned_pdf_extraction_warnings": list(extraction.warnings),
                "deidentified_source_text": True,
            }
        )
    else:
        extraction_metadata.update(
            {
                "scanned_pdf_extraction_attempted": False,
                "scanned_pdf_extraction_status": "embedded_text_used",
            }
        )

    payload = RadiologyReportCreate(
        patient_id=patient_id,
        uploaded_by_user_id=current_user.id,
        report_date=report_date,
        modality=modality,
        body_part=body_part,
        report_text=report_text,
        file_name=filename,
        metadata_json=extraction_metadata,
    )
    report = await radiology_reports._persist_report(
        payload=payload,
        source_type=source_type,
        session=session,
        current_user=current_user,
    )
    await radiology_reports._store_original_file(
        report.id,
        content,
        "application/pdf",
        session,
    )
    await session.refresh(report)
    return report
