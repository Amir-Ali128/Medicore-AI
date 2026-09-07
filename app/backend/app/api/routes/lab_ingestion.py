"""Authenticated seven-source laboratory ingestion -> native C++ trust endpoints.

Every source is first normalized into ``medicore-canonical-lab-v1`` and then passed
through the deterministic native trust boundary. No source can bypass C++ validation
to become trusted clinical evidence.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

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
from app.domain.native_lab_engine import NativeLabUnavailable
from app.domain.openai_lab_extraction_service import OpenAILabExtractionError
from app.domain.universal_lab_ingestion import (
    ingest_document_bytes,
    ingest_generic_file,
    ingest_integration_payload,
    ingest_manual_payload,
    ingestion_capabilities,
)

router = APIRouter(
    prefix="/lab-ingestion",
    tags=["lab-ingestion"],
    dependencies=[Depends(get_current_active_user)],
)


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
    if isinstance(exc, (OpenAILabExtractionError, NativeLabUnavailable, RuntimeError)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


def _native_trust(canonical_case: dict[str, Any]) -> dict[str, Any]:
    return process_canonical_lab_case(canonical_case)


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


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    """Return ingress families plus the mandatory downstream native trust contract."""
    payload = ingestion_capabilities()
    payload["downstream_contract"] = NATIVE_TRUST_CONTRACT
    payload["native_trust_required"] = True
    return payload


@router.post("/enabiz-pdf", status_code=status.HTTP_201_CREATED)
async def ingest_enabiz_pdf(
    file: UploadFile = File(...),
    source_record_id: str | None = None,
) -> dict[str, Any]:
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await ingest_document_bytes(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_ENABIZ_PDF,
            source_record_id=source_record_id,
        )
        return _native_trust(canonical)
    except Exception as exc:  # translated into stable API errors below
        _raise_ingestion_error(exc)
        raise


@router.post("/file", status_code=status.HTTP_201_CREATED)
async def ingest_file_upload(
    file: UploadFile = File(...),
    source_record_id: str | None = None,
) -> dict[str, Any]:
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await ingest_generic_file(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_FILE_UPLOAD,
            source_record_id=source_record_id,
        )
        return _native_trust(canonical)
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/photo", status_code=status.HTTP_201_CREATED)
async def ingest_photo(
    file: UploadFile = File(...),
    source_record_id: str | None = None,
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
        return _native_trust(canonical)
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/screenshot", status_code=status.HTTP_201_CREATED)
async def ingest_screenshot(
    file: UploadFile = File(...),
    source_record_id: str | None = None,
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
        return _native_trust(canonical)
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def ingest_manual(payload: ManualLabIngestionInput) -> dict[str, Any]:
    try:
        canonical = ingest_manual_payload(
            labs=payload.labs,
            patient_age=payload.patient_age,
            patient_sex=payload.patient_sex,
            report_date=payload.report_date,
            source_record_id=payload.source_record_id,
        )
        return _native_trust(canonical)
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/email-attachment", status_code=status.HTTP_201_CREATED)
async def ingest_email_attachment(
    file: UploadFile = File(...),
    source_record_id: str | None = None,
) -> dict[str, Any]:
    """Ingest an already-authorized email attachment; no mailbox access occurs here."""
    content, media_type, file_name = await _read_file(file)
    try:
        canonical = await ingest_generic_file(
            content=content,
            media_type=media_type,
            file_name=file_name,
            source_type=SOURCE_EMAIL_ATTACHMENT,
            source_record_id=source_record_id,
        )
        return _native_trust(canonical)
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise


@router.post("/integration", status_code=status.HTTP_201_CREATED)
async def ingest_integration(payload: IntegrationLabIngestionInput) -> dict[str, Any]:
    """Accept HL7 ORU, embedded FHIR Observation data, or structured REST JSON."""
    try:
        canonical = ingest_integration_payload(
            integration_type=payload.integration_type,
            payload=payload.payload,
            source_record_id=payload.source_record_id,
        )
        return _native_trust(canonical)
    except Exception as exc:
        _raise_ingestion_error(exc)
        raise
