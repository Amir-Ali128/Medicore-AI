"""Experimental X-ray / ultrasound image-review endpoint.

The endpoint is intentionally assistive: it stores non-diagnostic visual
observations next to the original image and always marks the record as requiring
physician review. If the AI service cannot return a usable review, the original
image is still archived instead of failing the whole upload.
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
    normalize_body_part,
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

_BODY_PART_LABELS = {
    "ABDOMEN": "Karın / batın",
    "CHEST": "Göğüs / toraks",
    "HEAD": "Baş / beyin",
    "NECK": "Boyun",
    "PELVIS": "Pelvis",
    "SPINE": "Omurga",
    "UPPER_EXTREMITY": "Üst ekstremite",
    "LOWER_EXTREMITY": "Alt ekstremite",
    "BREAST": "Meme",
    "THYROID": "Tiroid",
    "URINARY": "Üriner sistem / böbrek",
    "OBSTETRIC": "Obstetrik",
    "OTHER": "Diğer / belirsiz",
}


def _resolve_media_type(filename: str, content_type: str | None) -> str | None:
    normalized = (content_type or "").lower().strip()
    if normalized in SUPPORTED_IMAGE_MEDIA_TYPES:
        return normalized
    return _EXTENSION_TO_MEDIA_TYPE.get(Path(filename).suffix.lower())


def _infer_body_part_from_filename(filename: str) -> str | None:
    folded = (
        filename.upper()
        .replace("İ", "I")
        .replace("Ş", "S")
        .replace("Ğ", "G")
        .replace("Ü", "U")
        .replace("Ö", "O")
        .replace("Ç", "C")
    )
    keyword_groups = {
        "ABDOMEN": ("ABDOMEN", "ABDOMINAL", "BATIN", "KARIN"),
        "CHEST": ("CHEST", "THORAX", "TORAKS", "GOGUS"),
        "HEAD": ("HEAD", "BRAIN", "BEYIN", "KAFA"),
        "NECK": ("NECK", "BOYUN", "CERVICAL"),
        "PELVIS": ("PELVIS", "PELVIC"),
        "SPINE": ("SPINE", "OMURGA", "LOMBER", "LUMBAR"),
        "UPPER_EXTREMITY": ("KOL", "EL", "DIRSEK", "OMUZ", "UPPER EXTREMITY"),
        "LOWER_EXTREMITY": ("BACAK", "AYAK", "DIZ", "KALCA", "LOWER EXTREMITY"),
        "BREAST": ("BREAST", "MEME"),
        "THYROID": ("THYROID", "TIROID"),
        "URINARY": ("URINARY", "URINER", "BOBREK", "KIDNEY"),
        "OBSTETRIC": ("OBSTETRIC", "OBSTETRIK", "GEBELIK", "FETUS"),
    }
    for body_part, keywords in keyword_groups.items():
        if any(keyword in folded for keyword in keywords):
            return body_part
    return None


def _region_summary(body_part: str, summary: str) -> str:
    label = _BODY_PART_LABELS.get(body_part, body_part.replace("_", " ").title())
    clean_summary = " ".join(summary.split()).strip()
    return f"Bölge: {label}. {clean_summary}" if clean_summary else f"Bölge: {label}."


async def _save_ai_fallback(
    *,
    patient_id: uuid.UUID,
    report_date: date | None,
    normalized_modality: str,
    body_part: str | None,
    filename: str,
    media_type: str,
    content: bytes,
    session: SessionDep,
    current_user: User,
    reason: str,
) -> RadiologyReport:
    inferred_body_part = normalize_body_part(body_part) or _infer_body_part_from_filename(filename) or "OTHER"
    fallback_modality = None if normalized_modality == "AUTO" else normalized_modality

    report = await radiology_reports._persist_binary_file(
        patient_id=patient_id,
        report_date=report_date,
        modality=fallback_modality,
        body_part=inferred_body_part,
        filename=filename,
        content_type=media_type,
        content=content,
        session=session,
        current_user=current_user,
    )

    report.source_type = "image_ai_fallback"
    report.summary = _region_summary(
        inferred_body_part,
        "AI ön değerlendirmesi tamamlanamadı; görüntü kaybedilmeden dosya olarak kaydedildi ve hekim incelemesi gerekir.",
    )
    metadata = dict(report.metadata_json or {})
    metadata.update(
        {
            "analysis_available": False,
            "visual_analysis_available": False,
            "visual_analysis_fallback": True,
            "visual_analysis_error": reason[:800],
            "requested_modality": normalized_modality,
            "requested_body_part": normalize_body_part(body_part),
            "detected_body_part": inferred_body_part,
            "physician_review_required": True,
            "not_diagnostic": True,
        }
    )
    report.metadata_json = metadata
    await session.commit()
    await session.refresh(report)
    return report


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
    body_part: str | None = Form(None),
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

    requested_body_part = normalize_body_part(body_part) or _infer_body_part_from_filename(filename)

    try:
        review = await review_radiology_image(
            content=content,
            media_type=media_type,
            modality=normalized_modality,
            body_part=requested_body_part,
        )
    except Exception as exc:
        return await _save_ai_fallback(
            patient_id=patient_id,
            report_date=report_date,
            normalized_modality=normalized_modality,
            body_part=requested_body_part,
            filename=filename,
            media_type=media_type,
            content=content,
            session=session,
            current_user=current_user,
            reason=str(exc) or exc.__class__.__name__,
        )

    if review is None:
        return await _save_ai_fallback(
            patient_id=patient_id,
            report_date=report_date,
            normalized_modality=normalized_modality,
            body_part=requested_body_part,
            filename=filename,
            media_type=media_type,
            content=content,
            session=session,
            current_user=current_user,
            reason="AI görüntü modeli yapılandırılmamış veya geçici olarak kullanılamıyor.",
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
    stored_body_part = requested_body_part or review.detected_body_part or "OTHER"

    report = RadiologyReport(
        patient_id=patient_id,
        uploaded_by_user_id=current_user.id,
        source_type="image_ai_review",
        file_name=filename,
        report_date=report_date,
        modality=stored_modality,
        body_part=stored_body_part,
        original_text=review.visible_text,
        findings_json=findings,
        measurements_json=[],
        dexa_metrics_json=[],
        critical_findings_json=[],
        impression=None,
        summary=_region_summary(stored_body_part, review.summary),
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
            "requested_body_part": requested_body_part,
            "detected_body_part": review.detected_body_part,
            "supported_body_part": stored_body_part,
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
