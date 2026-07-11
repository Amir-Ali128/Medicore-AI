"""Phase 2 radiology report upload, analysis, persistence, and history routes."""

from __future__ import annotations

import io
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pypdf import PdfReader
from sqlalchemy import text as sql_text

from app.api.dependencies import SessionDep
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


async def _ensure_phase2_table(session: Any) -> None:
    """Create only the additive Phase 2 table on existing Render databases."""
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
                critical_findings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                impression TEXT,
                summary TEXT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'analyzed',
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
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


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Radiology PDF could not be read.") from exc

    text_parts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = "\n".join(part for part in text_parts if part).strip()
    if len(text) < 10:
        raise HTTPException(
            status_code=400,
            detail="No usable text was extracted. Scanned PDFs require OCR in a later phase.",
        )
    return text


async def _persist_report(
    *,
    payload: RadiologyReportCreate,
    source_type: str,
    session: SessionDep,
) -> RadiologyReport:
    await _ensure_phase2_table(session)
    await _ensure_demo_identity(session)

    if await session.get(Patient, payload.patient_id) is None:
        raise HTTPException(status_code=404, detail="Patient not found.")

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
        }
    )

    report = RadiologyReport(
        patient_id=payload.patient_id,
        uploaded_by_user_id=payload.uploaded_by_user_id,
        source_type=source_type,
        file_name=payload.file_name,
        report_date=payload.report_date,
        modality=payload.modality or analysis["modality"],
        body_part=payload.body_part or analysis["body_part"],
        original_text=payload.report_text,
        findings_json=analysis["findings"],
        measurements_json=analysis["measurements"],
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


@router.post(
    "/manual",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_radiology_report(
    payload: RadiologyReportCreate,
    session: SessionDep,
) -> RadiologyReport:
    return await _persist_report(
        payload=payload,
        source_type="manual_text",
        session=session,
    )


@router.post(
    "/upload",
    response_model=RadiologyReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_radiology_report(
    session: SessionDep,
    file: UploadFile = File(...),
    patient_id: uuid.UUID = Form(DEMO_PATIENT_ID),
    uploaded_by_user_id: uuid.UUID | None = Form(DEMO_UPLOADED_BY_USER_ID),
    report_date: date | None = Form(None),
    modality: str | None = Form(None),
    body_part: str | None = Form(None),
) -> RadiologyReport:
    filename = file.filename or "radiology-report.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF radiology reports are supported.")

    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Radiology PDF exceeds the 15 MB limit.")

    payload = RadiologyReportCreate(
        patient_id=patient_id,
        uploaded_by_user_id=uploaded_by_user_id,
        report_date=report_date,
        modality=modality,
        body_part=body_part,
        report_text=_extract_pdf_text(content),
        file_name=filename,
        metadata_json={
            "content_type": file.content_type,
            "upload_size_bytes": len(content),
        },
    )
    return await _persist_report(
        payload=payload,
        source_type="pdf_upload",
        session=session,
    )


@router.get(
    "/patient/{patient_id}",
    response_model=list[RadiologyReportResponse],
)
async def list_patient_radiology_reports(
    patient_id: uuid.UUID,
    session: SessionDep,
    limit: int = 50,
) -> list[RadiologyReport]:
    await _ensure_phase2_table(session)
    repository = RadiologyReportRepository(session)
    safe_limit = max(1, min(limit, 100))
    return list(await repository.list_for_patient(patient_id, limit=safe_limit))


@router.get("/{report_id}", response_model=RadiologyReportResponse)
async def get_radiology_report(
    report_id: uuid.UUID,
    session: SessionDep,
) -> RadiologyReport:
    await _ensure_phase2_table(session)
    repository = RadiologyReportRepository(session)
    report = await repository.get_by_id(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Radiology report not found.")
    return report
