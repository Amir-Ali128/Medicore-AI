"""Radiology/other report upload, analysis, persistence, and history routes."""

from __future__ import annotations

import io
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pypdf import PdfReader
from sqlalchemy import text as sql_text

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.domain.enums import Sex, UserRole
from app.domain.radiology_report_parser import analyze_radiology_report
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.radiology_report_repository import (
    RadiologyReportRepository,
)
from app.schemas.radiology_report import (
    DEMO_PATIENT_ID,
    DEMO_UPLOADED_BY_USER_ID,
    RadiologyReportCreate,
    RadiologyReportResponse,
)

router = APIRouter(prefix="/radiology-reports", tags=["radiology-reports"])

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024
_TEXT_EXTENSIONS = {
    ".txt",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".md",
    ".html",
    ".htm",
    ".log",
}


async def _ensure_phase2_table(session: Any) -> None:
    """Create/add Phase 2 columns on existing Render databases."""
    await session.execute(
        sql_text(
            """
            CREATE TABLE IF NOT EXISTS radiology_reports (
                id UUID PRIMARY KEY,
                patient_id UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                uploaded_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
                source_type VARCHAR(64) NOT NULL DEFAULT 'manual',
                file_name VARCHAR(512),
                report_date DATE,
                modality VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
                body_part VARCHAR(64) NOT NULL DEFAULT 'OTHER',
                original_text TEXT NOT NULL,
                findings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                measurements_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                dexa_metrics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                critical_findings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                impression TEXT,
                summary TEXT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'analyzed',
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                original_file_data BYTEA,
                original_file_content_type VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await session.execute(
        sql_text(
            "ALTER TABLE radiology_reports "
            "ADD COLUMN IF NOT EXISTS dexa_metrics_json JSONB NOT NULL DEFAULT '[]'::jsonb"
        )
    )
    await session.execute(
        sql_text(
            "ALTER TABLE radiology_reports ADD COLUMN IF NOT EXISTS original_file_data BYTEA"
        )
    )
    await session.execute(
        sql_text(
            "ALTER TABLE radiology_reports "
            "ADD COLUMN IF NOT EXISTS original_file_content_type VARCHAR(255)"
        )
    )
    await session.execute(
        sql_text(
            "CREATE INDEX IF NOT EXISTS ix_radiology_reports_patient_id "
            "ON radiology_reports (patient_id)"
        )
    )
    await session.execute(
        sql_text(
            "CREATE INDEX IF NOT EXISTS ix_radiology_reports_report_date "
            "ON radiology_reports (report_date)"
        )
    )


async def _ensure_demo_identity(session: Any) -> None:
    patient = await session.get(Patient, DEMO_PATIENT_ID)
    if patient is None:
        session.add(
            Patient(
                id=DEMO_PATIENT_ID,
                external_ref="demo-render-patient",
                sex=Sex.MALE,
                date_of_birth=date(2004, 1, 1),
                is_pregnant=False,
                metadata_json={"source": "phase2_radiology_auto_seed"},
            )
        )

    user = await session.get(User, DEMO_UPLOADED_BY_USER_ID)
    if user is None:
        session.add(
            User(
                id=DEMO_UPLOADED_BY_USER_ID,
                email="demo-upload@medicore.ai",
                hashed_password="not-used-demo-upload-user",
                full_name="Demo Upload User",
                role=UserRole.DOCTOR,
                is_active=True,
                is_superuser=False,
            )
        )
    await session.flush()


def _ensure_patient_access(patient: Patient, current_user: User) -> None:
    if current_user.role != UserRole.PATIENT:
        return

    owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
    if owner_user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")


async def _get_accessible_patient(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: User,
) -> Patient:
    if patient_id == DEMO_PATIENT_ID:
        await _ensure_demo_identity(session)

    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    _ensure_patient_access(patient, current_user)
    return patient


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="PDF dosyası okunamadı.") from exc

    text_parts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n".join(part for part in text_parts if part).strip()
    if len(text) < 10:
        raise HTTPException(
            status_code=400,
            detail="PDF'den kullanılabilir rapor metni çıkarılamadı.",
        )
    return text


def _decode_text_file(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            text = content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
        if len(text) >= 10:
            return text
    raise HTTPException(status_code=400, detail="Dosyadan kullanılabilir metin okunamadı.")


def _extract_upload_text(
    filename: str,
    content_type: str | None,
    content: bytes,
) -> tuple[str | None, str]:
    suffix = Path(filename).suffix.lower()
    normalized_content_type = (content_type or "").lower()

    if suffix == ".pdf" or normalized_content_type == "application/pdf":
        return _extract_pdf_text(content), "pdf_upload"

    if suffix in _TEXT_EXTENSIONS or normalized_content_type.startswith("text/"):
        return _decode_text_file(content), "text_file_upload"

    return None, "binary_file_upload"


async def _store_original_file(
    report_id: uuid.UUID,
    content: bytes,
    content_type: str | None,
    session: SessionDep,
) -> None:
    await session.execute(
        sql_text(
            """
            UPDATE radiology_reports
            SET original_file_data = :content,
                original_file_content_type = :content_type,
                updated_at = NOW()
            WHERE id = :report_id
            """
        ),
        {
            "report_id": str(report_id),
            "content": content,
            "content_type": content_type or "application/octet-stream",
        },
    )
    await session.commit()


async def _persist_report(
    *,
    payload: RadiologyReportCreate,
    source_type: str,
    session: SessionDep,
    current_user: User,
) -> RadiologyReport:
    await _ensure_phase2_table(session)
    await _get_accessible_patient(payload.patient_id, session, current_user)

    try:
        analysis = analyze_radiology_report(payload.report_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    metadata = dict(payload.metadata_json)
    metadata.update(
        {
            "parser_version": analysis["parser_version"],
            "parser_warnings": analysis["warnings"],
            "original_text_length": len(payload.report_text),
            "physician_review_required": True,
            "dexa_interpretation_is_assistive": bool(analysis["dexa_metrics"]),
            "analysis_available": True,
        }
    )

    report = RadiologyReport(
        patient_id=payload.patient_id,
        uploaded_by_user_id=current_user.id,
        source_type=source_type,
        file_name=payload.file_name,
        report_date=payload.report_date,
        modality=payload.modality or analysis["modality"],
        body_part=payload.body_part or analysis["body_part"],
        original_text=payload.report_text,
        findings_json=analysis["findings"],
        measurements_json=analysis["measurements"],
        dexa_metrics_json=analysis["dexa_metrics"],
        critical_findings_json=analysis["critical_findings"],
        impression=analysis["impression"],
        summary=analysis["summary"],
        status="needs_review" if analysis["critical_findings"] else "analyzed",
        metadata_json=metadata,
    )
    repository = RadiologyReportRepository(session)
    repository.create(report)
    await session.commit()
    await session.refresh(report)
    return report


async def _persist_binary_file(
    *,
    patient_id: uuid.UUID,
    report_date: date | None,
    modality: str | None,
    body_part: str | None,
    filename: str,
    content_type: str | None,
    content: bytes,
    session: SessionDep,
    current_user: User,
) -> RadiologyReport:
    await _ensure_phase2_table(session)
    await _get_accessible_patient(patient_id, session, current_user)

    report = RadiologyReport(
        patient_id=patient_id,
        uploaded_by_user_id=current_user.id,
        source_type="binary_file_upload",
        file_name=filename,
        report_date=report_date,
        modality=(modality or "UNKNOWN").strip().upper().replace("-", "_").replace(" ", "_"),
        body_part=(body_part or "OTHER").strip().upper().replace("-", "_").replace(" ", "_"),
        original_text="",
        findings_json=[],
        measurements_json=[],
        dexa_metrics_json=[],
        critical_findings_json=[],
        impression=None,
        summary="Dosya kaydedildi. Bu format için otomatik metin değerlendirmesi uygulanmadı.",
        status="file_saved",
        metadata_json={
            "content_type": content_type,
            "upload_size_bytes": len(content),
            "analysis_available": False,
            "original_file_stored": True,
            "physician_review_required": True,
        },
    )
    repository = RadiologyReportRepository(session)
    repository.create(report)
    await session.flush()
    await _store_original_file(report.id, content, content_type, session)
    await session.refresh(report)
    return report


@router.post(
    "/manual",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_radiology_report(
    payload: RadiologyReportCreate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> RadiologyReport:
    secured_payload = RadiologyReportCreate(
        patient_id=payload.patient_id,
        uploaded_by_user_id=current_user.id,
        report_date=payload.report_date,
        modality=payload.modality,
        body_part=payload.body_part,
        report_text=payload.report_text,
        file_name=payload.file_name,
        metadata_json=payload.metadata_json,
    )
    return await _persist_report(
        payload=secured_payload,
        source_type="manual_text",
        session=session,
        current_user=current_user,
    )


@router.post(
    "/upload",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_radiology_report(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
    patient_id: uuid.UUID = Form(DEMO_PATIENT_ID),
    report_date: date | None = Form(None),
    modality: str | None = Form(None),
    body_part: str | None = Form(None),
) -> RadiologyReport:
    filename = (file.filename or "uploaded-file").strip() or "uploaded-file"
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Boş dosya yüklenemez.")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Dosya 15 MB sınırını aşıyor.")

    report_text, source_type = _extract_upload_text(filename, file.content_type, content)

    if report_text is None:
        return await _persist_binary_file(
            patient_id=patient_id,
            report_date=report_date,
            modality=modality,
            body_part=body_part,
            filename=filename,
            content_type=file.content_type,
            content=content,
            session=session,
            current_user=current_user,
        )

    payload = RadiologyReportCreate(
        patient_id=patient_id,
        uploaded_by_user_id=current_user.id,
        report_date=report_date,
        modality=modality,
        body_part=body_part,
        report_text=report_text,
        file_name=filename,
        metadata_json={
            "content_type": file.content_type,
            "upload_size_bytes": len(content),
            "original_file_stored": True,
        },
    )
    report = await _persist_report(
        payload=payload,
        source_type=source_type,
        session=session,
        current_user=current_user,
    )
    await _store_original_file(report.id, content, file.content_type, session)
    await session.refresh(report)
    return report


@router.get(
    "/patient/{patient_id}",
    response_model=list[RadiologyReportResponse],
)
async def list_patient_radiology_reports(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = 50,
) -> list[RadiologyReport]:
    await _ensure_phase2_table(session)
    await _get_accessible_patient(patient_id, session, current_user)
    repository = RadiologyReportRepository(session)
    safe_limit = max(1, min(limit, 100))
    return list(await repository.list_for_patient(patient_id, limit=safe_limit))


@router.get("/{report_id}/file")
async def download_radiology_file(
    report_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    await _ensure_phase2_table(session)
    repository = RadiologyReportRepository(session)
    report = await repository.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Dosya bulunamadı.")
    await _get_accessible_patient(report.patient_id, session, current_user)

    row = (
        await session.execute(
            sql_text(
                "SELECT original_file_data, original_file_content_type "
                "FROM radiology_reports WHERE id = :report_id"
            ),
            {"report_id": str(report_id)},
        )
    ).mappings().one_or_none()
    if not row or row["original_file_data"] is None:
        raise HTTPException(status_code=404, detail="Bu kaydın özgün dosyası saklanmamış.")

    safe_name = (report.file_name or "dosya").replace('"', "").replace("\r", "").replace("\n", "")
    return Response(
        content=bytes(row["original_file_data"]),
        media_type=row["original_file_content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.get("/{report_id}", response_model=RadiologyReportResponse)
async def get_radiology_report(
    report_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> RadiologyReport:
    await _ensure_phase2_table(session)
    repository = RadiologyReportRepository(session)
    report = await repository.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Radiology report not found.")
    await _get_accessible_patient(report.patient_id, session, current_user)
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_radiology_report(
    report_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    await _ensure_phase2_table(session)
    repository = RadiologyReportRepository(session)
    report = await repository.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Radiology report not found.")
    await _get_accessible_patient(report.patient_id, session, current_user)

    await session.delete(report)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
