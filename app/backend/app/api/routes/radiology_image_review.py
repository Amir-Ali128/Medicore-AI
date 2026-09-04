"""Image upload endpoint for medical images and photographed report documents.

JPG/PNG/WEBP uploads are first classified as a written medical report page or a
true medical image. Report documents are de-identified, their explicit result /
impression section is stored separately, and additional source-derived findings
are retained. True medical images remain assistive and non-diagnostic.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import SessionDep
from app.api.routes import radiology_reports
from app.api.routes.auth import get_current_active_user
from app.core.config import get_settings
from app.domain.openai_radiology_second_reader import review_radiology_media_openai
from app.domain.radiology_image_ai import (
    SUPPORTED_IMAGE_MEDIA_TYPES,
    SUPPORTED_MODALITIES,
    normalize_body_part,
    normalize_image_modality,
)
from app.domain.radiology_provider_comparator import compare_radiology_readers
from app.domain.report_document_image_ai import RadiologyMediaReview, review_radiology_media
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.radiology_report_repository import (
    RadiologyReportRepository,
)
from app.infrastructure.runtime_resilience import get_anthropic_guard, get_openai_guard
from app.schemas.radiology_report import RadiologyReportResponse

router = APIRouter(prefix="/radiology-reports", tags=["radiology-image-review"])

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


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = " ".join(value.split()).strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _review_metadata(review: RadiologyMediaReview) -> dict[str, Any]:
    """Safe bounded snapshot for provider comparison/audit metadata."""
    return {
        "model": review.model,
        "document_kind": review.document_kind,
        "detected_modality": review.detected_modality,
        "detected_body_part": review.detected_body_part,
        "summary": review.summary,
        "observations": list(review.observations),
        "limitations": list(review.limitations),
        "physician_review_required": True,
        "not_diagnostic": True,
    }


async def _try_openai_review(
    *,
    content: bytes,
    media_type: str,
    modality: str,
    body_part: str | None,
) -> tuple[RadiologyMediaReview | None, str | None]:
    settings = get_settings()
    if (
        not settings.openai_radiology_second_reader_enabled
        or not settings.openai_api_key
        or not settings.openai_vision_model
    ):
        return None, "not_configured"

    try:
        review = await get_openai_guard("radiology-media").call(
            lambda: review_radiology_media_openai(
                content=content,
                media_type=media_type,
                modality=modality,
                body_part=body_part,
            )
        )
    except Exception as exc:
        return None, exc.__class__.__name__
    return review, None if review is not None else "not_configured"


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
    inferred_body_part = (
        normalize_body_part(body_part)
        or _infer_body_part_from_filename(filename)
        or "OTHER"
    )
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
        "AI ön değerlendirmesi tamamlanamadı; dosya kaybedilmeden arşivlendi ve hekim incelemesi gerekir.",
    )
    metadata = dict(report.metadata_json or {})
    metadata.update(
        {
            "analysis_available": False,
            "visual_analysis_available": False,
            "document_analysis_available": False,
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
            detail="Görüntü değerlendirmesi röntgen, ultrason veya otomatik içerik algılama ile kullanılabilir.",
        )

    media_type = _resolve_media_type(filename, file.content_type)
    if media_type is None:
        raise HTTPException(
            status_code=400,
            detail="Görüntü/rapor incelemesi için JPG, PNG veya WEBP yükleyin. DICOM ve diğer formatlar normal dosya yükleme ile arşivlenebilir.",
        )

    max_image_bytes = get_settings().radiology_image_max_bytes
    content = await file.read(max_image_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Boş görüntü yüklenemez.")
    if len(content) > max_image_bytes:
        max_megabytes = max_image_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Görüntü {max_megabytes} MB sınırını aşıyor.",
        )

    await radiology_reports._ensure_phase2_table(session)
    await radiology_reports._get_accessible_patient(patient_id, session, current_user)

    requested_body_part = normalize_body_part(body_part) or _infer_body_part_from_filename(filename)

    anthropic_review: RadiologyMediaReview | None = None
    anthropic_error: str | None = None
    try:
        anthropic_review = await get_anthropic_guard("radiology-media").call(
            lambda: review_radiology_media(
                content=content,
                media_type=media_type,
                modality=normalized_modality,
                body_part=requested_body_part,
            )
        )
    except Exception as exc:
        anthropic_error = exc.__class__.__name__

    review = anthropic_review
    primary_provider = "anthropic"
    second_reader: RadiologyMediaReview | None = None
    openai_error: str | None = None
    provider_comparison: dict[str, Any] | None = None

    if review is None:
        # Provider failover: a Claude outage/unconfigured deployment must not prevent
        # an independently configured OpenAI reader from preserving useful review.
        openai_review, openai_error = await _try_openai_review(
            content=content,
            media_type=media_type,
            modality=normalized_modality,
            body_part=requested_body_part,
        )
        if openai_review is not None:
            review = openai_review
            primary_provider = "openai_failover"
    elif review.document_kind == "MEDICAL_IMAGE":
        # Cost-aware second reader: written report photos stay on the primary OCR /
        # extraction path. True medical images receive an independent GPT review.
        second_reader, openai_error = await _try_openai_review(
            content=content,
            media_type=media_type,
            modality=normalized_modality,
            body_part=requested_body_part,
        )
        if second_reader is not None:
            if second_reader.document_kind == "MEDICAL_IMAGE":
                provider_comparison = compare_radiology_readers(review, second_reader)
            else:
                provider_comparison = {
                    "mode": "document_kind_mismatch",
                    "primary_document_kind": review.document_kind,
                    "second_reader_document_kind": second_reader.document_kind,
                    "requires_physician_attention": True,
                    "agreement_is_not_validation": True,
                }

    if review is None:
        fallback_reasons = [
            f"anthropic:{anthropic_error or 'not_configured'}",
            f"openai:{openai_error or 'not_configured'}",
        ]
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
            reason="; ".join(fallback_reasons),
        )

    is_document = review.document_kind == "REPORT_DOCUMENT"
    finding_texts = _dedupe(
        list(review.result_items) + list(review.key_findings)
        if is_document
        else list(review.observations)
    )
    findings = [
        {
            "text": text,
            "classification": "observation",
            "is_critical": False,
            "matched_terms": ["report_document"] if is_document else [],
        }
        for text in finding_texts[:40]
    ]

    stored_modality = (
        review.detected_modality
        if normalized_modality == "AUTO"
        else normalized_modality
    )
    if not stored_modality or stored_modality == "UNKNOWN":
        stored_modality = "UNKNOWN"
    stored_body_part = requested_body_part or review.detected_body_part or "OTHER"

    result_summary = review.result_text if is_document and review.result_text else review.summary
    source_type = "report_document_ai_review" if is_document else "image_ai_review"
    analysis_mode = (
        "multimodal_report_document_extraction"
        if is_document
        else "multimodal_dl_ml_assistive"
    )

    second_reader_metadata: dict[str, Any] = {
        "enabled": get_settings().openai_radiology_second_reader_enabled,
        "status": "available" if second_reader is not None else (
            "primary_failover" if primary_provider == "openai_failover" else (
                "not_configured" if openai_error == "not_configured" else "unavailable"
            )
        ),
        "provider": "openai",
    }
    if second_reader is not None:
        second_reader_metadata["review"] = _review_metadata(second_reader)
    if openai_error and openai_error != "not_configured":
        second_reader_metadata["error_type"] = openai_error

    report = RadiologyReport(
        patient_id=patient_id,
        uploaded_by_user_id=current_user.id,
        source_type=source_type,
        file_name=filename,
        report_date=report_date,
        modality=stored_modality,
        body_part=stored_body_part,
        original_text=review.visible_text,
        findings_json=findings,
        measurements_json=[],
        dexa_metrics_json=[],
        critical_findings_json=[],
        impression=review.result_text or None if is_document else None,
        summary=_region_summary(stored_body_part, result_summary),
        status="needs_review",
        metadata_json={
            "content_type": media_type,
            "upload_size_bytes": len(content),
            "original_file_stored": True,
            "analysis_available": True,
            "visual_analysis_available": not is_document,
            "document_analysis_available": is_document,
            "document_kind": review.document_kind,
            "report_type": review.report_type,
            "analysis_mode": analysis_mode,
            "analysis_provider": primary_provider,
            "analysis_model": review.model,
            "analysis_limitations": review.limitations,
            "result_text": review.result_text,
            "result_items": list(review.result_items),
            "key_findings": list(review.key_findings),
            "recommendations": list(review.recommendations),
            "comparison_text": review.comparison_text,
            "deidentified_visible_text": bool(review.visible_text),
            "physician_review_required": True,
            "not_diagnostic": True,
            "requested_modality": normalized_modality,
            "detected_modality": review.detected_modality,
            "supported_modality": stored_modality,
            "requested_body_part": requested_body_part,
            "detected_body_part": review.detected_body_part,
            "supported_body_part": stored_body_part,
            "openai_second_reader": second_reader_metadata,
            "provider_comparison": provider_comparison,
            "anthropic_primary_error_type": anthropic_error,
            "provider_agreement_is_not_ground_truth": True,
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
