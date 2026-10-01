"""API routes for the simplified MediCore case flow."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pypdf import PdfReader
from sqlalchemy import delete

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.domain.enums import ResultStatus, TrendStatus, UserRole
from app.domain.canonical_lab_model import SOURCE_FILE_UPLOAD
from app.domain.fast_pdf_lab_parser import try_fast_pdf_lab_case
from app.domain.openai_lab_extraction_service import (
    OpenAILabExtractionError,
    extract_lab_document_with_openai,
)
from app.domain.scanned_medical_report_pdf_ai import (
    ScannedMedicalReportExtractionError,
    extract_scanned_medical_report_pdf,
)
from app.domain.simple_case import case_fingerprint, normalize_simple_case
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
    *,
    content: bytes,
    file_name: str,
) -> dict | None:
    """Read an image-only lab PDF with the proven scanned-PDF vision path.

    The generic scanned-report extractor already falls back from OpenAI to the
    configured Anthropic page-vision reader. We then run the existing
    deterministic lab text parser over the extracted visible text.
    """

    try:
        extraction = await extract_scanned_medical_report_pdf(
            content=content,
            file_name=file_name,
        )
    except ScannedMedicalReportExtractionError:
        return None

    if extraction is None or not extraction.deidentified_text.strip():
        return None

    try:
        from app.api.routes.lab_analysis import _parse_lab_values_from_text

        parsed_rows = _parse_lab_values_from_text(extraction.deidentified_text)
    except Exception:
        return None

    rows: list[dict] = []
    for row in parsed_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("raw_parameter_name") or "").strip()
        raw_value = row.get("raw_value")
        if not name or raw_value in (None, ""):
            continue

        rows.append(
            {
                "raw_parameter_name": name,
                "raw_value": raw_value,
                "normalized_value": row.get("normalized_value"),
                "unit": row.get("unit") or row.get("extracted_unit"),
                "reference_min": row.get(
                    "reference_min",
                    row.get("extracted_reference_min"),
                ),
                "reference_max": row.get(
                    "reference_max",
                    row.get("extracted_reference_max"),
                ),
                "reference_text": row.get("reference_text"),
                "measured_at": row.get("measured_at"),
                "source_file_name": file_name,
                "source_page": row.get("source_page"),
                "needs_review": True,
                "confidence": extraction.confidence,
            }
        )

    if not rows:
        return None

    return {
        "labs": rows,
        "warnings": [
            *extraction.warnings,
            "scanned_pdf_vision_to_deterministic_lab_parser",
        ],
        "extraction_confidence": extraction.confidence,
    }


@router.post("/labs/pdf", response_model=list[LabResultInput])
async def upload_lab_pdf(
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
) -> list[LabResultInput]:
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
        extraction_source = "claude_pdf_vision"
        extracted = await _extract_lab_document_with_claude(
            content=content,
            file_name=file.filename or "lab.pdf",
        )

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
                    "PDF yerel parser ve Claude belge okuma ile güvenilir biçimde "
                    "ayrıştırılamadı; OpenAI fallback de kullanılamadı: "
                    f"{exc}"
                ),
            ) from exc

    rows: list[LabResultInput] = []
    for row in _dedupe_lab_rows(list(extracted.get("labs") or [])):
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
                measured_at=_parse_measured_at(row.get("measured_at")),
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
    patient.metadata_json = metadata

    await session.commit()
    await session.refresh(patient)
    return normalized
