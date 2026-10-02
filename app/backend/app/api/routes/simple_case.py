"""API routes for the simplified MediCore case flow."""

from __future__ import annotations

import io
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pypdf import PdfReader
from sqlalchemy import delete

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.core.config import get_settings
from app.domain.enums import ResultStatus, Sex, TrendStatus, UserRole
from app.domain.patient_clinical_context import patient_clinical_context
from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
from app.domain.canonical_lab_model import SOURCE_FILE_UPLOAD
from app.domain.fast_pdf_lab_parser import try_fast_pdf_lab_case
from app.domain.openai_lab_extraction_service import (
    OpenAILabExtractionError,
    extract_lab_document_with_openai,
)
from app.domain.report_document_image_ai import review_radiology_media
from app.domain.scanned_medical_report_pdf_ai import (
    ScannedMedicalReportExtractionError,
    extract_scanned_medical_report_pdf,
)
from app.domain.simple_case import case_fingerprint, normalize_simple_case
from app.domain.lab_document_ingestion import ingest_lab_document
from app.domain.lab_document_errors import reader_failure
from app.domain.lab_document_normalizer import DocumentPage
from app.domain.simple_case_ai import interpret_simple_case
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.infrastructure.database.models.user import User
from app.schemas.simple_case import (
    CaseAIInterpretationResponse,
    LabResultInput,
    MedicalReportInput,
    SimpleCaseRequest,
    SimpleCaseResponse,
)


router = APIRouter(prefix="/simple-case", tags=["simple-case"])
logger = logging.getLogger(__name__)

_MAX_PDF_BYTES = 15 * 1024 * 1024

_IGNORED_LAB_NAME_MARKERS = (
    "çalışılan hücre/doku",
    "calisilan hucre/doku",
    "çalışılan hücre",
    "calisilan hucre",
    "çalışılan doku",
    "calisilan doku",
    "ön sonuç",
    "on sonuc",
)


def _is_usable_lab_row(row: dict) -> bool:
    name = str(
        row.get("canonical_name")
        or row.get("raw_parameter_name")
        or ""
    ).strip()
    if not name:
        return False

    folded = (
        name.casefold()
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    if any(marker in folded for marker in _IGNORED_LAB_NAME_MARKERS):
        return False

    value = row.get("raw_value")
    if value in (None, ""):
        value = row.get("normalized_value")
    return value not in (None, "")


def _dedupe_lab_rows(rows: list[dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if not _is_usable_lab_row(row):
            continue
        name = str(row.get("canonical_name") or row.get("raw_parameter_name") or "").strip()
        value = row.get("raw_value")
        if value in (None, ""):
            value = row.get("normalized_value")
        unit = str(row.get("unit") or "").strip()
        reference = str(row.get("reference_text") or "").strip()
        key = (name.casefold(), str(value).strip(), unit.casefold(), reference.casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _parse_measured_at(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in (
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


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


def _decimal_or_none(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _date_or_none(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _report_modality(report_type: str) -> str:
    folded = report_type.upper().replace("İ", "I")
    aliases = (
        ("ULTRASON", "ULTRASOUND"),
        ("USG", "ULTRASOUND"),
        ("BT", "CT"),
        ("CT", "CT"),
        ("MR", "MRI"),
        ("MRI", "MRI"),
        ("RONTGEN", "XRAY"),
        ("XRAY", "XRAY"),
        ("EKG", "ECG"),
        ("ECG", "ECG"),
        ("EKO", "ECHO"),
        ("ECHO", "ECHO"),
    )
    for token, modality in aliases:
        if token in folded:
            return modality
    return "OTHER"


async def _persist_simple_case_sources(
    *,
    patient_id: uuid.UUID,
    normalized: SimpleCaseResponse,
    session: SessionDep,
    current_user: User,
) -> None:
    """Replace persisted simplified lab/report records for one patient."""

    await session.execute(
        delete(LabReport).where(
            LabReport.patient_id == patient_id,
            LabReport.source_type == "simple_case_pdf",
        )
    )
    await session.execute(
        delete(RadiologyReport).where(
            RadiologyReport.patient_id == patient_id,
            RadiologyReport.source_type == "simple_case_report",
        )
    )
    await session.flush()

    if normalized.labs:
        source_files = [
            str(item.source_metadata.get("source_file_name"))
            for item in normalized.labs
            if item.source_metadata.get("source_file_name")
        ]
        lab_report = LabReport(
            patient_id=patient_id,
            uploaded_by_user_id=current_user.id,
            source_type="simple_case_pdf",
            file_name=source_files[0] if source_files else "laboratuvar.pdf",
            report_date=_date_or_none(normalized.labs[0].measured_at),
            raw_payload={
                "contract_version": normalized.contract_version,
                "labs": [item.model_dump(mode="json") for item in normalized.labs],
            },
            status="saved",
            metadata_json={
                "simple_case": True,
                "source_files": list(dict.fromkeys(source_files)),
                "classification_disabled": True,
                "simple_case_results": [
                    {
                        "test_name": item.test_name,
                        "value": item.value,
                        "unit": item.unit,
                        "reference_text": item.reference_text,
                        "measured_at": (
                            item.measured_at.isoformat()
                            if hasattr(item.measured_at, "isoformat")
                            else item.measured_at
                        ),
                    }
                    for item in normalized.labs
                ],
            },
        )
        session.add(lab_report)
        await session.flush()

        lab_rows: list[LabResult] = []
        for item in normalized.labs:
            lab_rows.append(
                LabResult(
                    patient_id=patient_id,
                    lab_report_id=lab_report.id,
                    analysis_run_id=None,
                    parameter_id=None,
                    raw_parameter_name=item.test_name,
                    parameter_code=None,
                    canonical_name=item.test_name,
                    raw_value=None if item.value is None else str(item.value),
                    normalized_value=_decimal_or_none(item.value),
                    unit=item.unit,
                    reference_min=None,
                    reference_max=None,
                    reference_source=item.reference_source,
                    result_status=ResultStatus.UNKNOWN,
                    trend_status=TrendStatus.NO_PREVIOUS_RESULT,
                    previous_value=None,
                    absolute_difference=None,
                    percentage_difference=None,
                    time_difference_days=None,
                    alias_confidence=0.0,
                    reference_confidence=1.0 if item.reference_text else 0.0,
                    classification_confidence=0.0,
                    trend_confidence=0.0,
                    needs_review=True,
                    reason=None,
                    rule_applied=None,
                    measured_at=_date_or_none(item.measured_at),
                    metadata_json={
                        **dict(item.source_metadata or {}),
                        "simple_case": True,
                        "reference_text": item.reference_text,
                        "reference_details": (
                            item.reference_details.model_dump(mode="json")
                            if item.reference_details is not None
                            else None
                        ),
                        "classification_disabled": True,
                    },
                )
            )
        session.add_all(lab_rows)

    for report in normalized.reports:
        source_text = (report.raw_text or report.findings or report.impression or "").strip()
        if not source_text:
            continue
        metadata = dict(report.metadata or {})
        file_name = metadata.get("source_file_name")
        session.add(
            RadiologyReport(
                patient_id=patient_id,
                uploaded_by_user_id=current_user.id,
                source_type="simple_case_report",
                file_name=str(file_name) if file_name else None,
                report_date=_date_or_none(report.report_date),
                modality=_report_modality(report.report_type),
                body_part=(report.body_region or "OTHER").strip().upper().replace(" ", "_"),
                original_text=source_text,
                findings_json=(
                    [{"text": report.findings, "classification": "source_finding"}]
                    if report.findings
                    else []
                ),
                measurements_json=[],
                dexa_metrics_json=[],
                critical_findings_json=[],
                impression=report.impression,
                summary=(report.impression or report.findings or source_text)[:4000],
                status="saved",
                metadata_json={
                    **metadata,
                    "simple_case": True,
                    "report_type": report.report_type,
                    "physician_review_required": True,
                },
            )
        )

    await session.flush()


@router.get("/patients/{patient_id}")
async def get_saved_simple_case(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    """Return the persisted simple-case snapshot and saved AI report."""

    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    if current_user.role == UserRole.PATIENT:
        owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
        if owner_user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    metadata = dict(patient.metadata_json or {})
    saved_case = metadata.get("simple_case")
    ai_report = metadata.get("simple_case_ai_report")
    if (
        not isinstance(saved_case, dict)
        or not isinstance(ai_report, dict)
        or ai_report.get("case_fingerprint") != case_fingerprint(saved_case)
    ):
        ai_report = None
    return {
        "patient_id": str(patient.id),
        "protocol_no": patient.protocol_no,
        "sex": str(patient.sex.value if hasattr(patient.sex, "value") else patient.sex),
        "age": metadata.get("age"),
        "clinical": patient_clinical_context({
            **metadata, "sex": str(patient.sex),
        }).model_dump(mode="json"),
        "simple_case": metadata.get("simple_case"),
        "ai_report": ai_report,
    }


@router.post("/normalize", response_model=SimpleCaseResponse)
async def normalize_case(payload: SimpleCaseRequest) -> SimpleCaseResponse:
    """Normalize clinical + lab + report data without diagnostic classification."""

    return normalize_simple_case(payload)


@router.post("/ai-interpretation", response_model=CaseAIInterpretationResponse)
async def ai_interpret_case(
    payload: SimpleCaseRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CaseAIInterpretationResponse:
    """Synthesize clinical + lab + reports for clinician review."""

    try:
        result = await interpret_simple_case(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI klinik yorum tamamlanamadı: {exc}",
        ) from exc

    return CaseAIInterpretationResponse(
        report_text=result.report_text,
        model=result.model,
    )


@router.post(
    "/patients/{patient_id}/ai-interpretation",
    response_model=CaseAIInterpretationResponse,
)
async def ai_interpret_patient_case(
    patient_id: uuid.UUID,
    payload: SimpleCaseRequest,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CaseAIInterpretationResponse:
    """Generate and persist the physician-style AI report for a saved patient case."""

    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    if current_user.role == UserRole.PATIENT:
        owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
        if owner_user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    try:
        result = await interpret_simple_case(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI klinik yorum tamamlanamadı: {exc}",
        ) from exc

    metadata = dict(patient.metadata_json or {})
    metadata["simple_case_ai_report"] = {
        "report_text": result.report_text,
        "model": result.model,
        "generated_at": datetime.now(UTC).isoformat(),
        "case_fingerprint": case_fingerprint(
            normalize_simple_case(payload).model_dump(mode="json")
        ),
    }
    patient.metadata_json = metadata
    await session.commit()
    await session.refresh(patient)

    return CaseAIInterpretationResponse(
        report_text=result.report_text,
        model=result.model,
    )


async def _extract_lab_document_with_claude(
    *, content: bytes, file_name: str, media_type: str = "application/pdf",
) -> dict:
    """Read laboratory rows and retain safe failure diagnostics for fallback."""
    settings = get_settings()
    model = (settings.claude_extraction_model or settings.claude_vision_model or "").strip()
    try:
        service = ClaudeLabExtractionService(api_key=settings.anthropic_api_key, model=model)
        result = await service.extract_from_bytes(content, file_name, media_type)
    except Exception as exc:
        failure = reader_failure("Claude", exc)
        logger.warning("lab_reader_failed reader=Claude code=%s status=%s", failure['code'], failure['status'])
        return {"labs": [], "warnings": ["claude_extraction_failed"], "extraction_errors": [failure]}

    rows = []
    for item in result.values:
        ref_min, ref_max = item.extracted_reference_min, item.extracted_reference_max
        reference_text = item.reference_text
        if not reference_text:
            if ref_min is not None and ref_max is not None:
                reference_text = f"{ref_min} - {ref_max}"
            elif ref_min is not None:
                reference_text = f">= {ref_min}"
            elif ref_max is not None:
                reference_text = f"<= {ref_max}"
        rows.append({
            "raw_parameter_name": (item.raw_parameter_name or "").strip(),
            "raw_value": item.raw_value,
            "normalized_value": float(item.normalized_value) if item.normalized_value is not None else None,
            "unit": item.unit or item.extracted_unit,
            "reference_unit": item.extracted_unit,
            "reference_min": float(ref_min) if ref_min is not None else None,
            "reference_max": float(ref_max) if ref_max is not None else None,
            "reference_text": reference_text,
            "measured_at": item.measured_at.isoformat() if item.measured_at is not None else None,
            "source_file_name": result.source_file_name or file_name,
            "source_page": None,
            "needs_review": item.needs_review or result.overall_needs_review,
            "confidence": result.extraction_confidence,
            "source_flag": item.source_flag,
        })
    errors = []
    if not rows:
        invalid = any('parse' in warning.lower() or 'schema' in warning.lower() for warning in result.warnings)
        code = "invalid_response" if invalid else "no_rows"
        failure = {"reader": "Claude", "code": code, "message": (
            "Claude: belge okuma yanıtı ayrıştırılamadı." if invalid else
            "Claude: belgede okunabilir laboratuvar satırı bulunamadı."
        )}
        errors.append(failure)
        logger.warning("lab_reader_failed reader=Claude code=%s", code)
    return {
        "labs": rows, "warnings": [*result.warnings, "claude_lab_document_extraction"],
        "extraction_confidence": result.extraction_confidence,
        "visible_row_count": result.visible_row_count, "extraction_errors": errors,
    }


def _lab_inputs_from_extracted(
    extracted: dict,
    *,
    source_file_name: str | None,
    extraction_source: str,
) -> list[LabResultInput]:
    rows: list[LabResultInput] = []
    for row in list(extracted.get("labs") or []):
        if not isinstance(row, dict):
            continue

        test_name = str(
            row.get("canonical_name")
            or row.get("raw_parameter_name")
            or ""
        ).strip()
        if not test_name:
            test_name = "[Okunamayan parametre]"

        raw_value = row.get("raw_value")
        value = raw_value if raw_value not in (None, "") else row.get("normalized_value")

        reference_text = (
            str(row.get("reference_text")).strip()
            if row.get("reference_text")
            else None
        )

        if reference_text:
            reference_payload_text = reference_text
        elif row.get("reference_min") is not None and row.get("reference_max") is not None:
            reference_payload_text = f"{row.get('reference_min')} - {row.get('reference_max')}"
        elif row.get("reference_min") is not None:
            reference_payload_text = f">= {row.get('reference_min')}"
        elif row.get("reference_max") is not None:
            reference_payload_text = f"<= {row.get('reference_max')}"
        else:
            reference_payload_text = None

        rows.append(
            LabResultInput(
                test_name=test_name,
                value=value,
                unit=(str(row.get("unit")).strip() if row.get("unit") else None),
                measured_at=_parse_measured_at(row.get("measured_at")),
                source_reference=reference_text or reference_payload_text,
                source_references=(
                    [
                        {
                            "text": reference_payload_text,
                            "minimum": row.get("reference_min"),
                            "maximum": row.get("reference_max"),
                            "unit": (
                                str(row.get("reference_unit") or row.get("unit")).strip()
                                if row.get("reference_unit") or row.get("unit")
                                else None
                            ),
                        }
                    ]
                    if reference_payload_text
                    else []
                ),
                source_metadata={
                    "source_file_name": row.get("source_file_name") or source_file_name,
                    "source_page": row.get("source_page"),
                    "extraction_confidence": row.get("confidence"),
                    "needs_review": row.get("needs_review"),
                    "extraction_source": extraction_source,
                    "reference_min": row.get("reference_min"),
                    "reference_max": row.get("reference_max"),
                    "source_flag": row.get("source_flag"),
                    "raw_parameter_name": row.get("raw_parameter_name"),
                    "raw_value": row.get("raw_value"),
                    "source_sha256": row.get("source_sha256"),
                    "source_locations": row.get("source_locations", []),
                    "ingestion_reasons": row.get("ingestion_reasons", []),
                    "ingestion_contract": extracted.get("ingestion_contract"),
                    "document_warnings": extracted.get("warnings", []),
                    "page_reports": extracted.get("page_reports", []),
                    "raw_row_count": extracted.get("raw_row_count"),
                    "duplicate_count": extracted.get("duplicate_count"),
                },
            )
        )
    return rows


async def _ingest_lab_upload(file: UploadFile, media_type: str, *, rotation: int = 0) -> list[LabResultInput]:
    content = await file.read(_MAX_PDF_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Belge boş.")
    if len(content) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Belge 15 MB sınırını aşıyor.")
    file_name = file.filename or ("lab.pdf" if media_type == "application/pdf" else "lab-image.png")

    async def extract_page(page: DocumentPage) -> dict | None:
        # A PDF page may have selectable text while the next page is a scan.
        if page.native_pdf is not None:
            import asyncio
            native = await asyncio.to_thread(
                try_fast_pdf_lab_case, content=page.native_pdf, media_type="application/pdf",
                file_name=file_name, source_type=SOURCE_FILE_UPLOAD,
            )
            if native and native.get("labs"):
                return native
        # Reading-only provider: never route laboratory tables through radiology interpretation.
        result = await _extract_lab_document_with_claude(
            content=page.image, file_name=file_name, media_type="image/png",
        )
        if result and result.get("labs"):
            return result
        try:
            fallback = await extract_lab_document_with_openai(
                content=page.image, media_type="image/png", file_name=file_name,
            )
        except (OpenAILabExtractionError, ValueError) as exc:
            failure = reader_failure("OpenAI", exc)
            logger.warning("lab_reader_failed reader=OpenAI code=%s status=%s page=%s", failure['code'], failure['status'], page.number)
            return {"labs": [], "warnings": ["page_extraction_failed"],
                    "extraction_errors": [*(result or {}).get('extraction_errors', []), failure]}
        if not fallback.get('labs'):
            return {"labs": [], "warnings": ["page_extraction_failed"], "extraction_errors": [
                *(result or {}).get('extraction_errors', []),
                {"reader": "OpenAI", "code": "no_rows", "message": "OpenAI: belgede okunabilir laboratuvar satırı bulunamadı."},
            ]}
        return fallback

    try:
        extracted = await ingest_lab_document(
            content=content, media_type=media_type, file_name=file_name,
            extract_page=extract_page, rotation=rotation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _lab_inputs_from_extracted(extracted, source_file_name=file_name, extraction_source="lab_document_ingestion_v2")


@router.post("/labs/pdf", response_model=list[LabResultInput])
async def upload_lab_pdf(
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
) -> list[LabResultInput]:
    media_type = (file.content_type or "").split(";", 1)[0].lower()
    if media_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Laboratuvar dosyası PDF olmalıdır.")
    return await _ingest_lab_upload(file, media_type)


@router.post("/labs/image", response_model=list[LabResultInput])
async def upload_lab_image(
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
    rotation: int = Form(0),
) -> list[LabResultInput]:
    media_type = (file.content_type or "").split(";", 1)[0].lower()
    if media_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="Laboratuvar fotoğrafı JPG, PNG veya WEBP olmalıdır.")
    return await _ingest_lab_upload(file, media_type, rotation=rotation)


@router.post("/reports/pdf", response_model=MedicalReportInput)
async def upload_report_pdf(
    current_user: Annotated[User, Depends(get_current_active_user)],
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

    try:
        text = _extract_pdf_text(content)
        source_type = "pdf_text"
        detected_report_type = report_type.strip() or "Tıbbi Rapor"
        warnings: list[str] = []
        confidence = None
        model = None
    except HTTPException as exc:
        if exc.status_code != 400:
            raise
        try:
            extraction = await extract_scanned_medical_report_pdf(
                content=content,
                file_name=file.filename or "medical-report.pdf",
            )
        except ScannedMedicalReportExtractionError as extraction_exc:
            raise HTTPException(
                status_code=422,
                detail=str(extraction_exc),
            ) from extraction_exc

        if extraction is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "PDF taranmış/görüntü tabanlı ve görüntüden metin çıkarma "
                    "sağlayıcısı yapılandırılmamış."
                ),
            )

        text = extraction.deidentified_text
        source_type = "scanned_pdf_vision"
        detected_report_type = (
            report_type.strip()
            if report_type.strip() and report_type.strip() != "Tıbbi Rapor"
            else extraction.document_type
        )
        warnings = list(extraction.warnings)
        confidence = extraction.confidence
        model = extraction.model

    return MedicalReportInput(
        report_type=detected_report_type or "Tıbbi Rapor",
        body_region=body_region.strip() if body_region else None,
        findings=text,
        impression=None,
        raw_text=text,
        metadata={
            "source_file_name": file.filename,
            "source_type": source_type,
            "extraction_warnings": warnings,
            "extraction_confidence": confidence,
            "extraction_model": model,
        },
    )



@router.post("/reports/image", response_model=MedicalReportInput)
async def upload_report_image(
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
    report_type: str = Form("Tıbbi Rapor"),
    body_region: str | None = Form(None),
) -> MedicalReportInput:
    """Extract a photographed written medical report or review a medical image."""

    media_type = (file.content_type or "").split(";", 1)[0].lower()
    if media_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(
            status_code=400,
            detail="Tetkik fotoğrafı JPG, PNG veya WEBP olmalıdır.",
        )

    content = await file.read(_MAX_PDF_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Fotoğraf dosyası boş.")
    if len(content) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Fotoğraf 15 MB sınırını aşıyor.")

    try:
        review = await review_radiology_media(
            content=content,
            media_type=media_type,
            modality="AUTO",
            body_part=body_region,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Fotoğraf değerlendirilemedi: {exc}",
        ) from exc

    if review is None:
        raise HTTPException(
            status_code=422,
            detail="Fotoğraf okuma sağlayıcısı yapılandırılmamış veya dosya desteklenmiyor.",
        )

    requested_type = report_type.strip() or "Tıbbi Rapor"
    detected_type = (
        review.report_type
        if requested_type == "Tıbbi Rapor" and review.report_type != "UNKNOWN"
        else requested_type
    )

    if review.document_kind == "REPORT_DOCUMENT":
        source_text = review.visible_text or review.result_text or review.summary
        findings = source_text
        impression = review.result_text or None
        source_type = "report_photo_vision"
    else:
        source_text = "\n".join(
            [
                review.summary,
                *review.observations,
                *(["Sınırlılıklar: " + "; ".join(review.limitations)] if review.limitations else []),
            ]
        ).strip()
        findings = source_text
        impression = review.summary
        source_type = "medical_image_vision"

    return MedicalReportInput(
        report_type=detected_type or "Tıbbi Rapor",
        body_region=(
            body_region.strip()
            if body_region
            else (review.detected_body_part if review.detected_body_part != "OTHER" else None)
        ),
        findings=findings,
        impression=impression,
        raw_text=source_text,
        metadata={
            "source_file_name": file.filename,
            "source_type": source_type,
            "document_kind": review.document_kind,
            "detected_modality": review.detected_modality,
            "extraction_model": review.model,
            "limitations": review.limitations,
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

    previous = patient_clinical_context({**(patient.metadata_json or {}), "sex": str(patient.sex)})
    # Additive fields must survive requests from clients that do not know them.
    preserved = {
        name: getattr(previous, name) for name in previous.__class__.model_fields
        if name not in payload.clinical.model_fields_set
    }
    if preserved:
        payload = payload.model_copy(update={
            "clinical": payload.clinical.model_copy(update=preserved),
        })
    normalized = normalize_simple_case(payload)
    await _persist_simple_case_sources(
        patient_id=patient_id,
        normalized=normalized,
        session=session,
        current_user=current_user,
    )
    metadata = dict(patient.metadata_json or {})
    case_snapshot = normalized.model_dump(mode="json")
    ai_report = metadata.get("simple_case_ai_report")
    if (
        not isinstance(ai_report, dict)
        or ai_report.get("case_fingerprint") != case_fingerprint(case_snapshot)
    ):
        metadata.pop("simple_case_ai_report", None)
    metadata["clinical_context"] = normalized.clinical.model_dump(mode="json")
    metadata["simple_case"] = case_snapshot
    metadata["simple_case_contract_version"] = normalized.contract_version
    metadata["age"] = normalized.clinical.age
    # Legacy height/weight have now been read into the canonical measurements.
    metadata.pop("height_cm", None)
    metadata.pop("weight_kg", None)
    patient.sex = Sex(normalized.clinical.sex)
    patient.metadata_json = metadata

    await session.commit()
    await session.refresh(patient)
    return normalized
