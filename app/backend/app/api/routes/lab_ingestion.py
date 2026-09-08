"""Authenticated seven-source laboratory ingestion -> C++ trust -> history -> AI.

Every source is normalized into ``medicore-canonical-lab-v1`` and must cross the
native C++ trust boundary. When ``patient_id`` is supplied, trusted longitudinal
comparisons are resolved from PostgreSQL before clinical synthesis and the complete
source/trust/trend/AI snapshot is persisted atomically to the patient's history.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.core.config import get_settings
from app.domain.canonical_lab_model import (
    SOURCE_EMAIL_ATTACHMENT,
    SOURCE_ENABIZ_PDF,
    SOURCE_FILE_UPLOAD,
    SOURCE_PHOTO,
    SOURCE_SCREENSHOT,
)
from app.domain.canonical_native_trust import (
    NATIVE_TRUST_CONTRACT,
    process_canonical_lab_case,
)
from app.domain.fast_pdf_lab_parser import try_fast_pdf_lab_case
from app.domain.native_lab_engine import NativeLabUnavailable
from app.domain.native_trust_clinical_ai import (
    NATIVE_TRUST_CLINICAL_AI_CONTRACT,
    run_native_trust_clinical_pipeline,
)
from app.domain.openai_lab_extraction_service import OpenAILabExtractionError
from app.domain.patient_lab_history import (
    PATIENT_LAB_HISTORY_CONTRACT,
    build_longitudinal_trends,
    ensure_patient_access,
    persist_patient_lab_case,
)
from app.domain.universal_lab_ingestion import (
    ingest_document_bytes,
    ingest_generic_file,
    ingest_integration_payload,
    ingest_manual_payload,
    ingestion_capabilities,
)
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.user import User

router = APIRouter(
    prefix="/lab-ingestion",
    tags=["lab-ingestion"],
    dependencies=[Depends(get_current_active_user)],
)
CurrentUserDep = Annotated[User, Depends(get_current_active_user)]


class ManualLabIngestionInput(BaseModel):
    labs: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    patient_age: float | None = Field(default=None, ge=0, le=130)
    patient_sex: str | None = Field(default=None, max_length=32)
    report_date: str | None = Field(default=None, max_length=64)
    source_record_id: str | None = Field(default=None, max_length=256)


class IntegrationLabIngestionInput(BaseModel):
    integration_type: str = Field(min_length=2, max_length=32)
    payload: Any
    source_record_id: str | None = Field(default=None, max_length=256)


def _raise_ingestion_error(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, (OpenAILabExtractionError, NativeLabUnavailable, RuntimeError)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


async def _finalize_canonical_case(
    canonical_case: dict[str, Any],
    *,
    clinical_ai: bool,
    patient_id: uuid.UUID | None,
    session: SessionDep,
    current_user: User,
) -> dict[str, Any]:
    trust_envelope = process_canonical_lab_case(canonical_case)

    patient = None
    longitudinal_trends: list[dict[str, Any]] = []
    if patient_id is not None:
        patient = await ensure_patient_access(
            session,
            patient_id=patient_id,
            current_user=current_user,
        )
        longitudinal_trends = await build_longitudinal_trends(
            session,
            patient=patient,
            trust_envelope=trust_envelope,
        )

    if clinical_ai:
        result = await run_native_trust_clinical_pipeline(
            trust_envelope,
            longitudinal_trends=longitudinal_trends,
        )
    else:
        result = dict(trust_envelope)
        result["longitudinal_trends"] = longitudinal_trends

    if patient is not None:
        persistence = await persist_patient_lab_case(
            session,
            patient=patient,
            current_user=current_user,
            canonical_case=canonical_case,
            trust_envelope=trust_envelope,
            longitudinal_trends=longitudinal_trends,
            clinical_pipeline=result if clinical_ai else None,
        )
        result["patient_history"] = persistence
        result["history_contract_version"] = PATIENT_LAB_HISTORY_CONTRACT

    return result


async def _read_file(file: UploadFile) -> tuple[bytes, str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Dosya adı bulunamadı.")

    settings = get_settings()
    max_bytes = int(settings.lab_extraction_max_bytes)
    content = await file.read(max_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Yüklenen laboratuvar dosyası boş.")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Laboratuvar dosyası izin verilen "
                f"{max_bytes // (1024 * 1024)} MB sınırını aşıyor."
            ),
        )
    return content, file.content_type or "application/octet-stream", file.filename[:512]


async def _ingest_file_with_fast_pdf_fallback(
    *,
    content: bytes,
    media_type: str,
    file_name: str,
    source_type: str,
    source_record_id: str | None,
    generic: bool,
) -> dict[str, Any]:
    """Prefer deterministic local parsing for text PDFs, then fall back to AI."""
    fast_case = try_fast_pdf_lab_case(
        content=content,
        media_type=media_type,
        file_name=file_name,
        source_type=source_type,
        source_record_id=source_record_id,
    )
    if fast_case is not None:
        return fast_case

    if generic:
        return await ingest_generic_file(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=source_type,
            source_record_id=source_record_id,
        )

    return await ingest_document_bytes(
        content=content,
        media_type=media_type,
        file_name=file_name,
        source_type=source_type,
        source_record_id=source_record_id,
    )


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    payload = ingestion_capabilities()
    payload["downstream_contract"] = NATIVE_TRUST_CONTRACT
    payload["native_trust_required"] = True
    payload["clinical_ai_optional"] = True
    payload["clinical_ai_query_parameter"] = "clinical_ai=true"
    payload["clinical_pipeline_contract"] = NATIVE_TRUST_CLINICAL_AI_CONTRACT
    payload["patient_history_optional"] = True
    payload["patient_history_query_parameter"] = "patient_id=<uuid>"
    payload["patient_history_contract"] = PATIENT_LAB_HISTORY_CONTRACT
    payload["text_pdf_fast_path"] = True
    payload["text_pdf_fast_path_version"] = "fast_pdf_local_parser_v1"
    payload["saved_report_evaluation"] = True
    payload["saved_report_evaluation_endpoint"] = "/lab-ingestion/reports/{lab_report_id}/evaluate"
    return payload


@router.post("/enabiz-pdf", status_code=status.HTTP_201_CREATED)
async def ingest_enabiz_pdf(
    session: SessionDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
    source_record_id: str | None = None,
    clinical_ai: bool = False,
    patient_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await _ingest_file_with_fast_pdf_fallback(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_ENABIZ_PDF,
            source_record_id=source_record_id,
            generic=False,
        )
        return await _finalize_canonical_case(
            canonical,
            clinical_ai=clinical_ai,
            patient_id=patient_id,
            session=session,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/file", status_code=status.HTTP_201_CREATED)
async def ingest_file_upload(
    session: SessionDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
    source_record_id: str | None = None,
    clinical_ai: bool = False,
    patient_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await _ingest_file_with_fast_pdf_fallback(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_FILE_UPLOAD,
            source_record_id=source_record_id,
            generic=True,
        )
        return await _finalize_canonical_case(
            canonical,
            clinical_ai=clinical_ai,
            patient_id=patient_id,
            session=session,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/photo", status_code=status.HTTP_201_CREATED)
async def ingest_photo(
    session: SessionDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
    source_record_id: str | None = None,
    clinical_ai: bool = False,
    patient_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await ingest_document_bytes(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_PHOTO,
            source_record_id=source_record_id,
        )
        return await _finalize_canonical_case(
            canonical,
            clinical_ai=clinical_ai,
            patient_id=patient_id,
            session=session,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/screenshot", status_code=status.HTTP_201_CREATED)
async def ingest_screenshot(
    session: SessionDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
    source_record_id: str | None = None,
    clinical_ai: bool = False,
    patient_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await ingest_document_bytes(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_SCREENSHOT,
            source_record_id=source_record_id,
        )
        return await _finalize_canonical_case(
            canonical,
            clinical_ai=clinical_ai,
            patient_id=patient_id,
            session=session,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def ingest_manual(
    payload: ManualLabIngestionInput,
    session: SessionDep,
    current_user: CurrentUserDep,
    clinical_ai: bool = False,
    patient_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    try:
        canonical = ingest_manual_payload(
            labs=payload.labs,
            patient_age=payload.patient_age,
            patient_sex=payload.patient_sex,
            report_date=payload.report_date,
            source_record_id=payload.source_record_id,
        )
        return await _finalize_canonical_case(
            canonical,
            clinical_ai=clinical_ai,
            patient_id=patient_id,
            session=session,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/email-attachment", status_code=status.HTTP_201_CREATED)
async def ingest_email_attachment(
    session: SessionDep,
    current_user: CurrentUserDep,
    file: UploadFile = File(...),
    source_record_id: str | None = None,
    clinical_ai: bool = False,
    patient_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Ingest an already-authorized email attachment; no mailbox access occurs here."""
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await _ingest_file_with_fast_pdf_fallback(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_EMAIL_ATTACHMENT,
            source_record_id=source_record_id,
            generic=True,
        )
        return await _finalize_canonical_case(
            canonical,
            clinical_ai=clinical_ai,
            patient_id=patient_id,
            session=session,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/integration", status_code=status.HTTP_201_CREATED)
async def ingest_integration(
    payload: IntegrationLabIngestionInput,
    session: SessionDep,
    current_user: CurrentUserDep,
    clinical_ai: bool = False,
    patient_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Accept HL7 ORU, embedded FHIR Observation data, or structured REST JSON."""
    try:
        canonical = ingest_integration_payload(
            integration_type=payload.integration_type,
            payload=payload.payload,
            source_record_id=payload.source_record_id,
        )
        return await _finalize_canonical_case(
            canonical,
            clinical_ai=clinical_ai,
            patient_id=patient_id,
            session=session,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/reports/{lab_report_id}/evaluate")
async def evaluate_saved_lab_report(
    lab_report_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict[str, Any]:
    """Evaluate a persisted lab report without trusting client-supplied lab facts."""
    try:
        report = await session.get(LabReport, lab_report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Laboratuvar raporu bulunamadı.")

        await ensure_patient_access(
            session,
            patient_id=report.patient_id,
            current_user=current_user,
        )

        canonical_case = report.raw_payload
        if not isinstance(canonical_case, dict):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Kaydedilmiş rapor yeniden değerlendirilebilecek canonical veri taşımıyor.",
            )

        trust_envelope = process_canonical_lab_case(canonical_case)
        report_metadata = dict(report.metadata_json or {})
        stored_trends = report_metadata.get("longitudinal_trends")
        longitudinal_trends = (
            [dict(item) for item in stored_trends if isinstance(item, dict)]
            if isinstance(stored_trends, list)
            else []
        )

        result = await run_native_trust_clinical_pipeline(
            trust_envelope,
            longitudinal_trends=longitudinal_trends,
        )

        report_metadata["clinical_pipeline"] = {
            "contract_version": result.get("contract_version"),
            "clinical_assessment": result.get("clinical_assessment"),
            "ai_attempted": bool(result.get("ai_attempted")),
            "ai_used": bool(result.get("ai_used")),
            "native_trends_used_by_ai": int(result.get("native_trends_used_by_ai") or 0),
        }
        report.metadata_json = report_metadata
        report.status = "analyzed"
        await session.commit()

        result["patient_history"] = {
            "contract_version": PATIENT_LAB_HISTORY_CONTRACT,
            "patient_id": str(report.patient_id),
            "lab_report_id": str(report.id),
            "persisted_result_count": int(trust_envelope.get("processed_row_count") or 0),
            "trusted_count": int(trust_envelope.get("trusted_count") or 0),
            "review_count": int(trust_envelope.get("review_count") or 0),
            "trend_count": len(longitudinal_trends),
            "doctor_review_required": bool(int(trust_envelope.get("review_count") or 0)),
        }
        result["history_contract_version"] = PATIENT_LAB_HISTORY_CONTRACT
        return result
    except Exception as exc:
        await session.rollback()
        _raise_ingestion_error(exc)
        raise
