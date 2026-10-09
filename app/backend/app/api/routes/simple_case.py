"""API routes for the simplified MediCore case flow."""

from __future__ import annotations

import io
import hashlib
import json
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pypdf import PdfReader
from pydantic import ValidationError
from sqlalchemy import select

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.core.config import get_settings
from app.domain.enums import ResultStatus, Sex, TrendStatus, UserRole
from app.domain.case_management import case_display_name
from app.domain.document_dates import (
    SEMANTIC_DATE_FIELDS, calendar_day, date_values, extract_document_dates, resolve_timeline_date,
)
from app.domain.patient_clinical_context import normalize_patient_clinical, patient_clinical_context
from app.domain.clinical_record_dates import stamp_clinical_record_dates
from app.domain.patient_lab_history import ensure_patient_access
from app.domain.patient_scope import (
    SOURCE_MODELS, source_references, validate_source_metadata,
)
from app.domain.report_type_inference import infer_report_type
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
from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.infrastructure.database.models.user import User
from app.schemas.simple_case import (
    CaseAIInterpretationResponse,
    ClinicalContext,
    LabResultInput,
    MedicalReportInput,
    SimpleCaseRequest,
    SimpleCaseResponse,
)
from app.schemas.radiology_report import DEMO_PATIENT_ID


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
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
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
    return calendar_day(value)


def _restore_case_input(snapshot: dict) -> SimpleCaseRequest:
    """Read old normalized snapshots through today's additive input contract."""
    labs = []
    for raw in snapshot.get("labs") or []:
        if not isinstance(raw, dict):
            continue
        lab = dict(raw)
        if "source_reference" not in lab:
            lab["source_reference"] = lab.get("reference_text") or lab.get("raw_reference")
        if "source_references" not in lab and isinstance(lab.get("reference_details"), dict):
            lab["source_references"] = [lab["reference_details"]]
        labs.append(lab)
    raw_clinical = snapshot.get("clinical") or {}
    if any(key in raw_clinical for key in ("complaints", "history", "medications", "notes", "vital_signs")):
        # Preserve valid canonical input exactly, including timestamp precision
        # and text, so a fresh AI fingerprint still matches the saved case.
        try:
            clinical = ClinicalContext.model_validate(raw_clinical).model_dump()
        except ValidationError:
            clinical = normalize_patient_clinical(raw_clinical).model_dump()
    else:
        clinical = normalize_patient_clinical(raw_clinical).model_dump()
    return SimpleCaseRequest.model_validate({
        "clinical": clinical, "labs": labs,
        "reports": snapshot.get("reports") or [],
    })


def _semantic_date_metadata(item) -> dict:
    values = date_values(item.model_dump())
    return {key: (value.isoformat() if hasattr(value, "isoformat") else value)
            for key in SEMANTIC_DATE_FIELDS if (value := values.get(key)) is not None}


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


def _source_fingerprint(value) -> str:
    def meaningful_dates(item):
        if isinstance(item, dict):
            return {key: meaningful_dates(value) for key, value in item.items()
                    if key not in SEMANTIC_DATE_FIELDS or value is not None}
        if isinstance(item, list):
            return [meaningful_dates(value) for value in item]
        return item
    encoded = json.dumps(meaningful_dates(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ensure_actual_case_patient(patient_id: uuid.UUID) -> None:
    if patient_id == DEMO_PATIENT_ID:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")


async def _validate_case_patient_sources(
    payload: SimpleCaseRequest, session: SessionDep, current_user: User,
    patient_id: uuid.UUID | None = None,
    raw_payload: dict | None = None,
) -> None:
    """Reject mixed patient references before persisting or paying for AI."""
    metadata = raw_payload if raw_payload is not None else [
        *(item.source_metadata for item in payload.labs),
        *(item.metadata for item in payload.reports),
    ]
    references = set(source_references(metadata))
    if patient_id is None:
        # The standalone endpoint accepts unsaved text, but persisted references
        # must still resolve to exactly one accessible patient.
        patients = {source_id for source_type, source_id in references if source_type == "patient"}
        for source_type, source_id in references:
            if source_type == "patient":
                continue
            record = await session.get(SOURCE_MODELS[source_type], source_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Hasta veri kaynağı bulunamadı.")
            if source_type == "doctor_review":
                record = await session.get(ClinicalHypothesis, record.clinical_hypothesis_id)
                if record is None:
                    raise HTTPException(status_code=404, detail="Hasta veri kaynağı bulunamadı.")
            patients.add(record.patient_id)
        if len(patients) > 1:
            raise HTTPException(status_code=409, detail="Farklı hastaların verileri birlikte kullanılamaz.")
        patient_id = next(iter(patients), None)
    if patient_id is not None:
        _ensure_actual_case_patient(patient_id)
        await ensure_patient_access(session, patient_id=patient_id, current_user=current_user)
        await validate_source_metadata(session, patient_id=patient_id, metadata=metadata)


async def _persist_simple_case_sources(
    *,
    patient_id: uuid.UUID,
    normalized: SimpleCaseResponse,
    session: SessionDep,
    current_user: User,
) -> None:
    """Append distinct source sets; resaving never deletes a patient's history."""

    existing_labs = (
        await session.execute(select(LabReport).where(
            LabReport.patient_id == patient_id,
            LabReport.source_type == "simple_case_pdf",
        ))
    ).scalars().all()
    existing_lab_fingerprints = set()
    for report in existing_labs:
        stored_rows = (report.raw_payload or {}).get("labs", [])
        existing_lab_fingerprints.add(_source_fingerprint(stored_rows))
        # Additive statuses/dates should not duplicate a pre-upgrade source.
        try:
            restored = normalize_simple_case(_restore_case_input({
                "clinical": normalized.clinical.model_dump(), "labs": stored_rows,
            }))
        except ValidationError:
            continue
        existing_lab_fingerprints.add(_source_fingerprint([
            item.model_dump(mode="json") for item in restored.labs
        ]))
    grouped_labs: dict[tuple[str, str | None], list] = {}
    # A document can contain different clinical dates. Keep each dated set intact
    # so adding a later report does not relabel or replace its earlier results.
    for item in normalized.labs:
        source = str(item.source_metadata.get("source_sha256")
                     or item.source_metadata.get("source_file_name") or "manual")
        measured_at = resolve_timeline_date(item.model_dump(), kind="lab").date
        key = (source, measured_at.isoformat() if measured_at else None)
        grouped_labs.setdefault(key, []).append(item)
    # Recognize pre-upgrade aggregate reports without duplicating their rows.
    all_labs_fingerprint = _source_fingerprint([
        item.model_dump(mode="json") for item in normalized.labs
    ])
    if all_labs_fingerprint in existing_lab_fingerprints:
        grouped_labs = {}

    for labs in grouped_labs.values():
        source_rows = [item.model_dump(mode="json") for item in labs]
        fingerprint = _source_fingerprint(source_rows)
        if fingerprint in existing_lab_fingerprints:
            continue
        source_files = [
            str(item.source_metadata.get("source_file_name"))
            for item in labs
            if item.source_metadata.get("source_file_name")
        ]
        lab_report = LabReport(
            patient_id=patient_id,
            uploaded_by_user_id=current_user.id,
            source_type="simple_case_pdf",
            file_name=source_files[0] if source_files else "laboratuvar.pdf",
            report_date=resolve_timeline_date(labs[0].model_dump(), kind="lab").date,
            raw_payload={
                "contract_version": normalized.contract_version,
                "labs": source_rows,
            },
            status="saved",
            metadata_json={
                "simple_case": True,
                "source_fingerprint": fingerprint,
                "source_files": list(dict.fromkeys(source_files)),
                "classification_method": "deterministic_source_reference",
                "simple_case_results": [
                    {
                        "test_name": item.test_name,
                        "value": item.value,
                        "unit": item.unit,
                        "reference_text": item.reference_text,
                        "status": item.status,
                        "reference_low": item.reference_low,
                        "reference_high": item.reference_high,
                        "raw_reference": item.raw_reference,
                        "reference_details": item.reference_details.model_dump(mode="json") if item.reference_details else None,
                        **_semantic_date_metadata(item),
                        "measured_at": (
                            item.measured_at.isoformat()
                            if hasattr(item.measured_at, "isoformat")
                            else item.measured_at
                        ),
                    }
                    for item in labs
                ],
            },
        )
        session.add(lab_report)
        await session.flush()

        lab_rows: list[LabResult] = []
        for item in labs:
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
                    reference_min=_decimal_or_none(item.reference_low),
                    reference_max=_decimal_or_none(item.reference_high),
                    reference_source=item.reference_source,
                    result_status=ResultStatus(item.status.lower()),
                    trend_status=TrendStatus.NO_PREVIOUS_RESULT,
                    previous_value=None,
                    absolute_difference=None,
                    percentage_difference=None,
                    time_difference_days=None,
                    alias_confidence=0.0,
                    reference_confidence=1.0 if item.reference_text else 0.0,
                    classification_confidence=1.0 if item.status != "UNKNOWN" else 0.0,
                    trend_confidence=0.0,
                    needs_review=item.status == "UNKNOWN" or bool(item.source_metadata.get("needs_review")),
                    reason=item.classification_reason,
                    rule_applied="deterministic_source_reference",
                    measured_at=resolve_timeline_date(item.model_dump(), kind="lab").date,
                    metadata_json={
                        **dict(item.source_metadata or {}),
                        "simple_case": True,
                        "reference_text": item.reference_text,
                        "status": item.status,
                        "reference_low": item.reference_low,
                        "reference_high": item.reference_high,
                        "raw_reference": item.raw_reference,
                        "original_measured_at": item.measured_at.isoformat() if item.measured_at else None,
                        **_semantic_date_metadata(item),
                        "reference_details": (
                            item.reference_details.model_dump(mode="json")
                            if item.reference_details is not None
                            else None
                        ),
                        "classification_method": "deterministic_source_reference",
                    },
                )
            )
        session.add_all(lab_rows)
        existing_lab_fingerprints.add(fingerprint)

    existing_reports = (
        await session.execute(select(RadiologyReport).where(
            RadiologyReport.patient_id == patient_id,
            RadiologyReport.source_type == "simple_case_report",
        ))
    ).scalars().all()
    report_fingerprints = {
        (report.metadata_json or {}).get("source_fingerprint")
        for report in existing_reports
    }

    for report in normalized.reports:
        source_text = report.raw_text or report.findings or report.impression or ""
        if not source_text.strip():
            continue
        metadata = dict(report.metadata or {})
        metadata.update({key: value for key, value in _semantic_date_metadata(report).items()})
        fingerprint = _source_fingerprint(report.model_dump(mode="json"))
        if fingerprint in report_fingerprints:
            continue
        # Older rows have no fingerprint; compare their original source fields.
        if any(
            stored.original_text == source_text
            and stored.report_date == _date_or_none(report.report_date)
            and stored.file_name == metadata.get("source_file_name")
            and (stored.metadata_json or {}).get("report_type") == report.report_type
            and stored.impression == report.impression
            for stored in existing_reports
            if not (stored.metadata_json or {}).get("source_fingerprint")
        ):
            continue
        metadata.update(infer_report_type(
            source_text=source_text, findings=report.findings,
            impression=report.impression, modality=report.report_type,
        ).to_metadata())
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
                    "source_fingerprint": fingerprint,
                    "report_type": report.report_type,
                    "physician_review_required": True,
                },
            )
        )
        report_fingerprints.add(fingerprint)

    await session.flush()


@router.get("/patients/{patient_id}")
async def get_saved_simple_case(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    """Return the persisted simple-case snapshot and saved AI report."""

    _ensure_actual_case_patient(patient_id)
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    if current_user.role == UserRole.PATIENT:
        owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
        if owner_user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    metadata = dict(patient.metadata_json or {})
    saved_case = metadata.get("simple_case")
    if isinstance(saved_case, dict):
        await validate_source_metadata(session, patient_id=patient_id, metadata=saved_case)
        try:
            saved_case = normalize_simple_case(_restore_case_input(saved_case)).model_dump(mode="json")
        except ValidationError:
            # Malformed historic snapshots remain readable; never trust an old
            # source/AI status when source values cannot be normalized safely.
            saved_case = {**saved_case, "labs": [
                {**item, "status": "UNKNOWN", "classification_reason": "legacy_validation_required"}
                for item in saved_case.get("labs", []) if isinstance(item, dict)
            ]}
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
        "case_name": case_display_name(patient.protocol_no, metadata),
        "sex": str(patient.sex.value if hasattr(patient.sex, "value") else patient.sex),
        "age": metadata.get("age"),
        "clinical": patient_clinical_context({
            **metadata, "sex": str(patient.sex),
        }).model_dump(mode="json"),
        "simple_case": saved_case,
        "ai_report": ai_report,
    }


@router.post("/normalize", response_model=SimpleCaseResponse)
async def normalize_case(payload: SimpleCaseRequest) -> SimpleCaseResponse:
    """Normalize source data and numeric ranges without clinical interpretation."""

    return normalize_simple_case(payload)


@router.post("/ai-interpretation", response_model=CaseAIInterpretationResponse)
async def ai_interpret_case(
    payload: SimpleCaseRequest,
    request: Request,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CaseAIInterpretationResponse:
    """Synthesize clinical + lab + reports for clinician review."""

    await _validate_case_patient_sources(
        payload, session, current_user, raw_payload=await request.json(),
    )
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
    request: Request,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CaseAIInterpretationResponse:
    """Generate and persist the physician-style AI report for a saved patient case."""

    _ensure_actual_case_patient(patient_id)
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    if current_user.role == UserRole.PATIENT:
        owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
        if owner_user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    await _validate_case_patient_sources(
        payload, session, current_user, patient_id, raw_payload=await request.json(),
    )
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
            **{key: (value.isoformat() if hasattr(value, "isoformat") else value)
               for key in SEMANTIC_DATE_FIELDS
               if (value := getattr(item, key, None)) is not None},
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
                **{key: _parse_measured_at(date_values(row).get(key)) for key in
                   ("event_date", "specimen_date", "result_date", "document_date", "uploaded_at")},
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
                    "reference_unit": row.get("reference_unit"),
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
    # Upload endpoints keep their v1 shape while returning the same canonical
    # status used by save/detail/AI. Demographic selection is refreshed on save.
    normalized = normalize_simple_case(SimpleCaseRequest(labs=rows))
    return [row.model_copy(update={
        "status": lab.status, "reference_low": lab.reference_low,
        "reference_high": lab.reference_high, "raw_reference": lab.raw_reference,
        "classification_reason": lab.classification_reason,
    }) for row, lab in zip(rows, normalized.labs)]


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
    uploaded_at = datetime.now(UTC).isoformat()
    for row in extracted.get("labs") or []:
        row["uploaded_at"] = uploaded_at
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

    dates = extract_document_dates(text)
    return MedicalReportInput(
        report_type=detected_report_type or "Tıbbi Rapor",
        **dates, uploaded_at=datetime.now(UTC),
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

    dates = extract_document_dates(source_text)
    return MedicalReportInput(
        report_type=detected_type or "Tıbbi Rapor",
        **dates, uploaded_at=datetime.now(UTC),
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
    request: Request,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SimpleCaseResponse:
    """Persist the latest simplified case snapshot on the patient record."""

    _ensure_actual_case_patient(patient_id)
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    if current_user.role == UserRole.PATIENT:
        owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
        if owner_user_id != str(current_user.id):
            raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    await _validate_case_patient_sources(
        payload, session, current_user, patient_id, raw_payload=await request.json(),
    )
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
    metadata = stamp_clinical_record_dates(metadata, previous, normalized.clinical)
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
