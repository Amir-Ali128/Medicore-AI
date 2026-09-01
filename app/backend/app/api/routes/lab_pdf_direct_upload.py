"""Fast, PDF-first laboratory upload path.

This endpoint intentionally avoids per-test dictionary/reference/trend database
round trips during initial PDF ingestion. Readable blood-test rows and supported
urinalysis rows are preserved and classified directly against the reference interval
printed in that report. Blood and urine counts remain separate in report metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.dependencies import SessionDep
from app.api.routes import lab_analysis, lab_pdf_system_extract
# Import for side effects: fixes no-reference rows, CBC #/% keys and footer rows.
from app.api.routes import lab_pdf_system_extract_runtime as _lab_pdf_runtime  # noqa: F401
from app.domain.enums import ResultStatus, TrendStatus
from app.infrastructure.database.models.analysis_run import AnalysisRun
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.schemas.lab_analysis import (
    AnalysisCounts,
    AnalysisPipelineResult,
    StructuredLabResultOutput,
)

router = APIRouter(prefix="/lab-analysis", tags=["lab-analysis"])

_PARSER_SOURCE = "pdf_direct_upload_v2_panels"


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _classify_row(row: dict[str, Any]) -> tuple[ResultStatus, bool, str, str | None]:
    value = _decimal(row.get("normalized_value"))
    low = _decimal(row.get("extracted_reference_min"))
    high = _decimal(row.get("extracted_reference_max"))

    if value is None:
        return (
            ResultStatus.NEEDS_REVIEW,
            True,
            "Sayısal sonuç okunamadı; hekim kontrolü gerekir.",
            "pdf_missing_numeric_value",
        )

    if low is None or high is None:
        return (
            ResultStatus.NEEDS_REVIEW,
            True,
            "PDF üzerinde güvenilir bir referans aralığı bulunmadığı için sonuç otomatik sınıflandırılmadı.",
            "pdf_missing_reference",
        )

    if value < low:
        return (
            ResultStatus.LOW,
            False,
            f"Değer {value}, PDF referans alt sınırı {low} değerinin altındadır.",
            "pdf_value_below_min",
        )
    if value > high:
        return (
            ResultStatus.HIGH,
            False,
            f"Değer {value}, PDF referans üst sınırı {high} değerinin üzerindedir.",
            "pdf_value_above_max",
        )
    return (
        ResultStatus.NORMAL,
        False,
        f"Değer {value}, PDF referans aralığı [{low}, {high}] içindedir.",
        "pdf_value_within_range",
    )


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
        needs_review=result.needs_review,
        reason=result.reason,
        alias_confidence=result.alias_confidence,
        reference_confidence=result.reference_confidence,
        classification_confidence=result.classification_confidence,
        trend_confidence=result.trend_confidence,
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
    if not file.filename:
        raise HTTPException(status_code=400, detail="Yüklenen dosyanın adı bulunmuyor.")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Bu akış yalnızca PDF dosyalarını destekler.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Yüklenen PDF boş.")
    if len(file_bytes) > lab_analysis._MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="PDF 10 MB sınırını aşıyor.",
        )

    extracted_text = lab_analysis._extract_text_from_pdf(file_bytes)
    if not extracted_text.strip():
        raise HTTPException(
            status_code=400,
            detail="PDF'den seçilebilir metin çıkarılamadı. Görüntü tabanlı PDF için OCR gerekir.",
        )

    report_date = lab_pdf_system_extract._extract_report_date(extracted_text)
    rows = lab_pdf_system_extract._parse_all_blood_rows(extracted_text, report_date)
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="PDF içinde sınıflandırılabilir laboratuvar veya idrar sonucu bulunamadı.",
        )

    blood_count = sum(1 for row in rows if row.get("panel") != "urinalysis")
    urinalysis_count = sum(1 for row in rows if row.get("panel") == "urinalysis")

    # The existing demo entities are used only as temporary ownership until the
    # user presses Kaydet and attaches the report to the active patient.
    await lab_analysis._ensure_demo_patient_and_user()
    patient_metadata = lab_analysis._parse_patient_metadata_from_text(extracted_text)

    now = datetime.now(timezone.utc)
    report = LabReport(
        patient_id=lab_analysis.DEMO_PATIENT_ID,
        uploaded_by_user_id=lab_analysis.DEMO_UPLOADED_BY_USER_ID,
        source_type="pdf_upload",
        file_name=file.filename,
        report_date=report_date,
        raw_payload={
            "source": _PARSER_SOURCE,
            "parsed_blood_test_count": blood_count,
            "parsed_urinalysis_count": urinalysis_count,
            "parsed_total_result_count": len(rows),
        },
        metadata_json={
            "parser_source": _PARSER_SOURCE,
            "parsed_blood_test_count": blood_count,
            "parsed_urinalysis_count": urinalysis_count,
            "parsed_total_result_count": len(rows),
            "reference_policy": "printed_pdf_reference_first",
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
        metadata_json={"source": _PARSER_SOURCE},
    )
    session.add(run)
    await session.flush()

    persisted: list[LabResult] = []
    for row in rows:
        result_status, needs_review, reason, rule = _classify_row(row)
        reference_min = _decimal(row.get("extracted_reference_min"))
        reference_max = _decimal(row.get("extracted_reference_max"))
        normalized_value = _decimal(row.get("normalized_value"))
        display_name = str(row.get("display_name") or "Bilinmeyen test")[:255]
        unit = str(row.get("unit") or "")[:64] or None

        lab_result = LabResult(
            patient_id=lab_analysis.DEMO_PATIENT_ID,
            lab_report_id=report.id,
            analysis_run_id=run.id,
            parameter_id=None,
            raw_parameter_name=display_name,
            parameter_code=None,
            canonical_name=display_name,
            raw_value=str(row.get("raw_value") or "")[:128] or None,
            normalized_value=normalized_value,
            unit=unit,
            reference_min=reference_min,
            reference_max=reference_max,
            reference_source="extracted_report" if reference_min is not None and reference_max is not None else None,
            result_status=result_status,
            trend_status=TrendStatus.NO_PREVIOUS_RESULT,
            previous_value=None,
            absolute_difference=None,
            percentage_difference=None,
            time_difference_days=None,
            alias_confidence=1.0,
            reference_confidence=0.98 if reference_min is not None and reference_max is not None else 0.0,
            classification_confidence=1.0 if not needs_review else 0.0,
            trend_confidence=0.0,
            needs_review=needs_review,
            reason=reason,
            rule_applied=rule,
            measured_at=report_date,
            metadata_json={
                "source": _PARSER_SOURCE,
                "panel": str(row.get("panel") or "blood"),
                "semiquantitative": bool(row.get("semiquantitative")),
                "qualitative_normal": bool(row.get("qualitative_normal")),
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
    )
