"""Astra-first laboratory document upload path.

The original PDF/image files are sent directly to the configured OpenAI multimodal
model for document reading, preprocessing, extraction and semantic normalization.
The returned rows are validated/classified and mathematically enriched by MediCore's
native C++ lab core before a second, physician-assistive AI synthesis. The legacy
Python PDF parser is intentionally not part of this route anymore.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.dependencies import SessionDep
from app.api.routes import lab_analysis
from app.core.config import get_settings
from app.domain.enums import ResultStatus, TrendStatus
from app.domain.native_lab_engine import (
    NativeLabUnavailable,
    compute_native_lab_metrics,
    process_astra_lab_rows,
)
from app.domain.openai_lab_clinical_service import (
    OpenAILabClinicalError,
    build_fallback_clinical_assessment,
    synthesize_lab_clinical_assessment,
)
from app.domain.openai_lab_extraction_service import (
    OpenAILabExtractionError,
    SUPPORTED_LAB_MEDIA_TYPES,
    extract_lab_documents_with_openai,
)
from app.infrastructure.database.models.analysis_run import AnalysisRun
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.schemas.lab_analysis import (
    AnalysisCounts,
    AnalysisPipelineResult,
    DerivedLabMetricOutput,
    LabClinicalAssessmentOutput,
    PatientMetadataOutput,
    StructuredLabResultOutput,
)

router = APIRouter(prefix="/lab-analysis", tags=["lab-analysis"])

_PARSER_SOURCE = "astra_native_cpp_lab_v2"
_EXTENSION_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _date(value: Any, fallback: date | None = None) -> date | None:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return fallback


def _media_type(file: UploadFile) -> str:
    declared = (file.content_type or "").split(";", 1)[0].lower().strip()
    if declared in SUPPORTED_LAB_MEDIA_TYPES:
        return declared
    suffix = Path(file.filename or "").suffix.lower()
    return _EXTENSION_MEDIA_TYPES.get(suffix, declared)


def _status(value: Any) -> ResultStatus:
    normalized = str(value or "").strip().upper()
    return {
        "NORMAL": ResultStatus.NORMAL,
        "LOW": ResultStatus.LOW,
        "HIGH": ResultStatus.HIGH,
        "NEEDS_REVIEW": ResultStatus.NEEDS_REVIEW,
    }.get(normalized, ResultStatus.UNKNOWN)


def _python_fallback(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Development-only fallback; production defaults to native_lab_required=true."""
    processed: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        value = _decimal(row.get("normalized_value"))
        low = _decimal(row.get("reference_min"))
        high = _decimal(row.get("reference_max"))
        confidence = float(row.get("confidence") or 0.0)
        needs_review = bool(row.get("needs_review")) or confidence < 0.85

        if value is None:
            result_status = "NEEDS_REVIEW"
            needs_review = True
            reason = "Sayısal sonuç güvenilir biçimde çıkarılamadı."
            rule = "python_fallback_missing_numeric"
            classification_confidence = 0.0
        elif low is not None and high is not None and low > high:
            result_status = "NEEDS_REVIEW"
            needs_review = True
            reason = "Referans aralığı geçersiz."
            rule = "python_fallback_invalid_reference"
            classification_confidence = 0.0
        elif low is not None and value < low:
            result_status = "LOW"
            reason = "Değer kaynak rapordaki referans alt sınırının altında."
            rule = "python_fallback_below_min"
            classification_confidence = confidence
        elif high is not None and value > high:
            result_status = "HIGH"
            reason = "Değer kaynak rapordaki referans üst sınırının üzerinde."
            rule = "python_fallback_above_max"
            classification_confidence = confidence
        elif low is not None or high is not None:
            result_status = "NORMAL"
            reason = "Değer kaynak rapordaki mevcut referans sınırları içinde."
            rule = "python_fallback_within_reference"
            classification_confidence = confidence
        else:
            result_status = "NEEDS_REVIEW"
            needs_review = True
            reason = "Kaynak raporda güvenilir referans sınırı bulunamadı."
            rule = "python_fallback_missing_reference"
            classification_confidence = 0.0

        processed.append(
            {
                **row,
                "display_name": row.get("canonical_name") or row.get("raw_parameter_name") or "Bilinmeyen test",
                "reference_min": low,
                "reference_max": high,
                "extraction_confidence": confidence,
                "result_status": result_status,
                "needs_review": needs_review,
                "reason": reason,
                "rule_applied": rule,
                "classification_confidence": classification_confidence,
                "contract_version": "python-development-fallback",
            }
        )
    return processed


def _to_output(result: LabResult) -> StructuredLabResultOutput:
    return StructuredLabResultOutput(
        lab_result_id=result.id,
        raw_parameter_name=result.raw_parameter_name,
        parameter_id=result.parameter_id,
        parameter_code=result.parameter_code,
        canonical_name=result.canonical_name,
        normalized_value=result.normalized_value,
        unit=result.unit,
        reference_min=result.reference_min,
        reference_max=result.reference_max,
        result_status=result.result_status,
        trend_status=result.trend_status,
        measured_at=result.measured_at,
        needs_review=result.needs_review,
        reason=result.reason,
        alias_confidence=result.alias_confidence,
        reference_confidence=result.reference_confidence,
        classification_confidence=result.classification_confidence,
        trend_confidence=result.trend_confidence,
    )


async def _prepare_uploads(files: list[UploadFile]) -> list[tuple[bytes, str, str]]:
    settings = get_settings()
    if not files:
        raise HTTPException(status_code=400, detail="En az bir laboratuvar dosyası yüklenmelidir.")

    prepared: list[tuple[bytes, str, str]] = []
    total_bytes = 0
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Yüklenen dosyalardan birinin adı bulunmuyor.")
        media_type = _media_type(file)
        if media_type not in SUPPORTED_LAB_MEDIA_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Desteklenmeyen laboratuvar dosyası: {file.filename}",
            )
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail=f"Yüklenen dosya boş: {file.filename}")
        total_bytes += len(file_bytes)
        prepared.append((file_bytes, media_type, file.filename))

    if total_bytes > settings.lab_extraction_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Laboratuvar dosyalarının toplamı "
                f"{settings.lab_extraction_max_bytes // (1024 * 1024)} MB sınırını aşıyor."
            ),
        )
    return prepared


async def _analyze_prepared_documents(
    *,
    session: SessionDep,
    documents: list[tuple[bytes, str, str]],
) -> AnalysisPipelineResult:
    settings = get_settings()
    if not settings.openai_lab_extraction_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Direct OpenAI/Astra laboratuvar çıkarımı devre dışı.",
        )

    try:
        ai_payload = await extract_lab_documents_with_openai(documents=documents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OpenAILabExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    raw_rows = ai_payload.get("labs") or []
    if not raw_rows:
        raise HTTPException(
            status_code=400,
            detail="Astra/OpenAI dosyalarda güvenilir laboratuvar sonucu bulamadı.",
        )

    try:
        rows = process_astra_lab_rows(raw_rows)
    except NativeLabUnavailable as exc:
        if settings.native_lab_required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        rows = _python_fallback([dict(row) for row in raw_rows])
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Native lab işleme hatası: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=400, detail="İşlenebilir laboratuvar satırı bulunamadı.")

    await lab_analysis._ensure_demo_patient_and_user()

    report_date = _date(ai_payload.get("report_date"), date.today()) or date.today()
    patient_metadata = PatientMetadataOutput(
        display_name=None,
        age=ai_payload.get("patient_age"),
        sex=(str(ai_payload.get("patient_sex")).strip() if ai_payload.get("patient_sex") else None),
        birth_date=None,
    )

    try:
        derived_metric_dicts = compute_native_lab_metrics(
            raw_rows,
            patient_age=patient_metadata.age,
            patient_sex=patient_metadata.sex,
        )
    except (NativeLabUnavailable, RuntimeError, ValueError) as exc:
        if settings.native_lab_required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Native C++ clinical metrics kullanılamıyor: {exc}",
            ) from exc
        derived_metric_dicts = []

    derived_metrics = [DerivedLabMetricOutput.model_validate(item) for item in derived_metric_dicts]

    try:
        clinical_assessment_dict = await synthesize_lab_clinical_assessment(
            rows=rows,
            derived_metrics=derived_metric_dicts,
            patient_age=patient_metadata.age,
            patient_sex=patient_metadata.sex,
        )
    except OpenAILabClinicalError:
        clinical_assessment_dict = build_fallback_clinical_assessment(
            rows=rows,
            derived_metrics=derived_metric_dicts,
        )
    clinical_assessment = LabClinicalAssessmentOutput.model_validate(clinical_assessment_dict)

    model_name = settings.openai_lab_model
    source_names = [name for _content, _media_type_value, name in documents]
    report_file_name = source_names[0] if len(source_names) == 1 else f"batch:{len(source_names)}-files"
    now = datetime.now(timezone.utc)
    safe_ai_metadata = {
        "model": model_name,
        "extraction_confidence": ai_payload.get("extraction_confidence"),
        "warnings": ai_payload.get("warnings") or [],
        "derived_metrics": [item.model_dump(mode="json") for item in derived_metrics],
        "clinical_assessment": clinical_assessment.model_dump(mode="json"),
    }

    report = LabReport(
        patient_id=lab_analysis.DEMO_PATIENT_ID,
        uploaded_by_user_id=lab_analysis.DEMO_UPLOADED_BY_USER_ID,
        source_type="ai_document_upload",
        file_name=report_file_name,
        report_date=report_date,
        raw_payload={
            "source": _PARSER_SOURCE,
            "source_files": source_names,
            "processed_lab_count": len(rows),
            **safe_ai_metadata,
        },
        metadata_json={
            "parser_source": _PARSER_SOURCE,
            "native_contract": rows[0].get("contract_version"),
            "native_metrics_contract": (
                derived_metric_dicts[0].get("metrics_version") if derived_metric_dicts else None
            ),
            "reference_policy": "source_document_reference_first",
            "source_file_count": len(source_names),
            **safe_ai_metadata,
        },
        status="analyzed",
    )
    session.add(report)
    await session.flush()

    run = AnalysisRun(
        patient_id=lab_analysis.DEMO_PATIENT_ID,
        lab_report_id=report.id,
        status="completed",
        started_at=now,
        completed_at=now,
        metadata_json={
            "source": _PARSER_SOURCE,
            "model": model_name,
            "source_file_count": len(source_names),
            "native_contract": rows[0].get("contract_version"),
            "native_metric_codes": [metric.code for metric in derived_metrics],
            "clinical_synthesis_source": clinical_assessment.synthesis_source,
        },
    )
    session.add(run)
    await session.flush()

    persisted: list[LabResult] = []
    for row in rows:
        result_status = _status(row.get("result_status"))
        needs_review = bool(row.get("needs_review"))
        reference_min = _decimal(row.get("reference_min"))
        reference_max = _decimal(row.get("reference_max"))
        normalized_value = _decimal(row.get("normalized_value"))
        display_name = str(
            row.get("display_name")
            or row.get("canonical_name")
            or row.get("raw_parameter_name")
            or "Bilinmeyen test"
        )[:255]
        raw_parameter_name = str(row.get("raw_parameter_name") or display_name)[:255]
        unit = str(row.get("unit") or "")[:64] or None
        extraction_confidence = float(row.get("extraction_confidence") or 0.0)
        classification_confidence = float(row.get("classification_confidence") or 0.0)
        measured_at = _date(row.get("measured_at"), report_date)

        lab_result = LabResult(
            patient_id=lab_analysis.DEMO_PATIENT_ID,
            lab_report_id=report.id,
            analysis_run_id=run.id,
            parameter_id=None,
            raw_parameter_name=raw_parameter_name,
            parameter_code=None,
            canonical_name=display_name,
            raw_value=str(row.get("raw_value") or "")[:128] or None,
            normalized_value=normalized_value,
            unit=unit,
            reference_min=reference_min,
            reference_max=reference_max,
            reference_source=(
                "extracted_report"
                if reference_min is not None or reference_max is not None
                else None
            ),
            result_status=result_status,
            trend_status=TrendStatus.NO_PREVIOUS_RESULT,
            previous_value=None,
            absolute_difference=None,
            percentage_difference=None,
            time_difference_days=None,
            alias_confidence=extraction_confidence,
            reference_confidence=(
                extraction_confidence
                if reference_min is not None or reference_max is not None
                else 0.0
            ),
            classification_confidence=classification_confidence,
            trend_confidence=0.0,
            needs_review=needs_review,
            reason=str(row.get("reason") or "")[:2000] or None,
            rule_applied=str(row.get("rule_applied") or "")[:255] or None,
            measured_at=measured_at,
            metadata_json={
                "source": _PARSER_SOURCE,
                "source_file_name": row.get("source_file_name"),
                "source_page": row.get("source_page"),
                "reference_text": row.get("reference_text"),
                "extraction_confidence": extraction_confidence,
                "native_contract": row.get("contract_version"),
            },
        )
        persisted.append(lab_result)

    session.add_all(persisted)
    await session.flush()

    counts = AnalysisCounts(
        total=len(persisted),
        normal=sum(1 for item in persisted if item.result_status == ResultStatus.NORMAL),
        low=sum(1 for item in persisted if item.result_status == ResultStatus.LOW),
        high=sum(1 for item in persisted if item.result_status == ResultStatus.HIGH),
        needs_review=sum(1 for item in persisted if item.needs_review),
        unknown=sum(1 for item in persisted if item.result_status == ResultStatus.UNKNOWN),
    )
    run.total_results = counts.total
    run.normal_count = counts.normal
    run.low_count = counts.low
    run.high_count = counts.high
    run.needs_review_count = counts.needs_review
    run.unknown_count = counts.unknown

    await session.commit()

    return AnalysisPipelineResult(
        analysis_run_id=run.id,
        lab_report_id=report.id,
        patient_id=lab_analysis.DEMO_PATIENT_ID,
        patient=patient_metadata,
        results=[_to_output(item) for item in persisted],
        counts=counts,
        derived_metrics=derived_metrics,
        clinical_assessment=clinical_assessment,
    )


@router.post(
    "/upload",
    response_model=AnalysisPipelineResult,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_uploaded_pdf_direct(
    session: SessionDep,
    file: UploadFile = File(...),
) -> AnalysisPipelineResult:
    """Backward-compatible single file endpoint; now Astra + C++ powered."""
    documents = await _prepare_uploads([file])
    return await _analyze_prepared_documents(session=session, documents=documents)


@router.post(
    "/upload-batch",
    response_model=AnalysisPipelineResult,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_uploaded_lab_batch(
    session: SessionDep,
    files: list[UploadFile] = File(...),
) -> AnalysisPipelineResult:
    """Send up to the model's batch limit of lab PDFs/images as one case."""
    documents = await _prepare_uploads(files)
    return await _analyze_prepared_documents(session=session, documents=documents)
