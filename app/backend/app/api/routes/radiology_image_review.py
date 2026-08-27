"""Experimental X-ray / ultrasound image-review endpoint.

The endpoint is intentionally assistive: it stores non-diagnostic visual
observations next to the original image and always marks the record as requiring
physician review.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import SessionDep
from app.api.routes import radiology_reports
from app.api.routes.auth import get_current_active_user
from app.domain.radiology_image_ai import (
    SUPPORTED_IMAGE_MEDIA_TYPES,
    SUPPORTED_MODALITIES,
    normalize_image_modality,
    review_radiology_image,
)
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.radiology_report_repository import (
    RadiologyReportRepository,
)
from app.schemas.radiology_report import RadiologyReportResponse

router = APIRouter(prefix="/radiology-reports", tags=["radiology-image-review"])

_MAX_IMAGE_BYTES = 15 * 1024 * 1024
_EXTENSION_TO_MEDIA_TYPE = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _resolve_media_type(filename: str, content_type: str | None) -> str | None:
    normalized = (content_type or "").lower().strip()
    if normalized in SUPPORTED_IMAGE_MEDIA_TYPES:
        return normalized
    return _EXTENSION_TO_MEDIA_TYPE.get(Path(filename).suffix.lower())


@router.post(
    "/image-review",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_radiology_image_review(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
    patient_id: uuid.UUID = Form(...),
    modality: str = Form(...),
    report_date: date | None = Form(None),
) -> RadiologyReport:
    filename = (file.filename or "radiology-image").strip() or "radiology-image"
    normalized_modality = normalize_image_modality(modality)
    if normalized_modality not in SUPPORTED_MODALITIES:
        raise HTTPException(
            status_code=400,
            detail="AI görüntü ön değerlendirmesi röntgen, ultrason veya otomatik modalite algılama ile kullanılabilir.",
        )

    media_type = _resolve_media_type(filename, file.content_type)
    if media_type is None:
        raise HTTPException(
            status_code=400,
            detail="AI görüntü ön değerlendirmesi için JPG, PNG veya WEBP yükleyin. DICOM ve diğer formatlar normal dosya yükleme ile arşivlenebilir.",
        )

    content = await file.read(_MAX_IMAGE_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Boş görüntü yüklenemez.")
    if len(content) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Görüntü 15 MB sınırını aşıyor.")

    await radiology_reports._ensure_phase2_table(session)
    await radiology_reports._get_accessible_patient(patient_id, session, current_user)

    try:
        review = await review_radiology_image(
            content=content,
            media_type=media_type,
            modality=normalized_modality,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI görüntü ön değerlendirmesi tamamlanamadı: {exc}",
        ) from exc

    if review is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI görüntü ön değerlendirmesi yapılandırılmamış. ANTHROPIC_API_KEY ve "
                "mevcut Claude model ayarlarından biri gerekli. İsterseniz ayrıca "
                "CLAUDE_VISION_MODEL tanımlayabilirsiniz."
            ),
        )

    findings = [
        {
            "text": observation,
            "classification": "observation",
            "is_critical": False,
            "matched_terms": [],
        }
        for observation in review.observations
    ]

    stored_modality = (
        review.detected_modality
        if normalized_modality == "AUTO"
        else normalized_modality
    )

    report = RadiologyReport(
        patient_id=patient_id,
        uploaded_by_user_id=current_user.id,
        source_type="image_ai_review",
        file_name=filename,
        report_date=report_date,
        modality=stored_modality,
        body_part="OTHER",
        original_text=review.visible_text,
        findings_json=findings,
        measurements_json=[],
        dexa_metrics_json=[],
        critical_findings_json=[],
        impression=None,
        summary=review.summary,
        status="needs_review",
        metadata_json={
            "content_type": media_type,
            "upload_size_bytes": len(content),
            "original_file_stored": True,
            "analysis_available": True,
            "visual_analysis_available": True,
            "analysis_mode": "multimodal_dl_ml_assistive",
            "analysis_model": review.model,
            "analysis_limitations": review.limitations,
            "physician_review_required": True,
            "not_diagnostic": True,
            "requested_modality": normalized_modality,
            "detected_modality": review.detected_modality,
            "supported_modality": stored_modality,
        },
    )
    repository = RadiologyReportRepository(session)
    repository.create(report)
    await session.flush()
    await radiology_reports._store_original_file(
        report.id,
        content,
        media_type,
        session,
    )
    await session.refresh(report)
    return report