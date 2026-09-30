"""API routes for the simplified MediCore case flow."""

from __future__ import annotations

import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pypdf import PdfReader

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.domain.enums import UserRole
from app.domain.canonical_lab_model import SOURCE_FILE_UPLOAD
from app.domain.fast_pdf_lab_parser import try_fast_pdf_lab_case
from app.domain.openai_lab_extraction_service import (
    OpenAILabExtractionError,
    extract_lab_document_with_openai,
)
from app.domain.simple_case import normalize_simple_case
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.schemas.simple_case import (
    LabResultInput,
    MedicalReportInput,
    SimpleCaseRequest,
    SimpleCaseResponse,
)


router = APIRouter(prefix="/simple-case", tags=["simple-case"])

_MAX_PDF_BYTES = 15 * 1024 * 1024


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="PDF dosyası okunamadı.") from exc

    text = "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    if len(text) < 10:
        raise HTTPException(
            status_code=400,
            detail="PDF dosyasından kullanılabilir metin çıkarılamadı.",
        )
    return text


@router.post("/normalize", response_model=SimpleCaseResponse)
async def normalize_case(payload: SimpleCaseRequest) -> SimpleCaseResponse:
    """Normalize clinical + lab + report data without diagnostic classification."""

    return normalize_simple_case(payload)


@router.post("/labs/pdf", response_model=list[LabResultInput])
async def upload_lab_pdf(file: UploadFile = File(...)) -> list[LabResultInput]:
    """Extract laboratory rows from a PDF without classifying their values."""

    if (file.content_type or "").split(";", 1)[0].lower() != "application/pdf":
        raise HTTPException(status_code=400, detail="Laboratuvar dosyası PDF olmalıdır.")

    content = await file.read(_MAX_PDF_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="PDF dosyası boş.")
    if len(content) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF dosyası 15 MB sınırını aşıyor.")

    extracted: dict | None = try_fast_pdf_lab_case(
        content=content,
        media_type="application/pdf",
        file_name=file.filename or "lab.pdf",
        source_type=SOURCE_FILE_UPLOAD,
    )

    extraction_source = "local_pdf_parser"

    if extracted is None:
        extraction_source = "openai_fallback"
        try:
            extracted = await extract_lab_document_with_openai(
                content=content,
                media_type="application/pdf",
                file_name=file.filename or "lab.pdf",
            )
        except (OpenAILabExtractionError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail=(
                    "PDF yerel olarak güvenilir biçimde ayrıştırılamadı ve AI fallback "
                    f"kullanılamadı: {exc}"
                ),
            ) from exc

    rows: list[LabResultInput] = []
    for row in extracted.get("labs") or []:
        if not isinstance(row, dict):
            continue

        test_name = str(
            row.get("canonical_name")
            or row.get("raw_parameter_name")
            or ""
        ).strip()
        if not test_name:
            continue

        raw_value = row.get("raw_value")
        value = raw_value if raw_value not in (None, "") else row.get("normalized_value")

        rows.append(
            LabResultInput(
                test_name=test_name,
                value=value,
                unit=(str(row.get("unit")).strip() if row.get("unit") else None),
                measured_at=row.get("measured_at"),
                source_reference=(
                    str(row.get("reference_text")).strip()
                    if row.get("reference_text")
                    else None
                ),
                source_metadata={
                    "source_file_name": row.get("source_file_name") or file.filename,
                    "source_page": row.get("source_page"),
                    "extraction_confidence": row.get("confidence"),
                    "needs_review": row.get("needs_review"),
                    "extraction_source": extraction_source,
                },
            )
        )

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="PDF içinde kullanılabilir laboratuvar sonucu bulunamadı.",
        )

    return rows


@router.post("/reports/pdf", response_model=MedicalReportInput)
async def upload_report_pdf(
    file: UploadFile = File(...),
    report_type: str = Form("Tıbbi Rapor"),
    body_region: str | None = Form(None),
) -> MedicalReportInput:
    """Extract text from a generic medical report PDF and add it to the case."""

    if (file.content_type or "").split(";", 1)[0].lower() != "application/pdf":
        raise HTTPException(status_code=400, detail="Tetkik raporu PDF olmalıdır.")

    content = await file.read(_MAX_PDF_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="PDF dosyası boş.")
    if len(content) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF dosyası 15 MB sınırını aşıyor.")

    text = _extract_pdf_text(content)

    return MedicalReportInput(
        report_type=report_type.strip() or "Tıbbi Rapor",
        body_region=body_region.strip() if body_region else None,
        findings=text,
        impression=None,
        raw_text=text,
        metadata={
            "source_file_name": file.filename,
            "source_type": "pdf_upload",
        },
    )


@router.put("/patients/{patient_id}/save", response_model=SimpleCaseResponse)
async def save_case_for_patient(
    patient_id: uuid.UUID,
    payload: SimpleCaseRequest,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SimpleCaseResponse:
    """Persist the latest simplified case snapshot on the patient record."""

    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    if current_user.role == UserRole.PATIENT:
        owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
        if owner_user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    normalized = normalize_simple_case(payload)
    metadata = dict(patient.metadata_json or {})
    metadata["clinical_context"] = normalized.clinical.model_dump(mode="json")
    metadata["simple_case"] = normalized.model_dump(mode="json")
    metadata["simple_case_contract_version"] = normalized.contract_version
    patient.metadata_json = metadata

    await session.commit()
    await session.refresh(patient)
    return normalized
