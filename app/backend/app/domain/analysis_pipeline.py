"""AnalysisPipeline.

Orchestrates the already-approved deterministic engines to turn a mock lab
report into structured, classified, and persisted lab results:

    AliasEngine -> ReferenceResolver -> RuleEngine -> TrendEngine

It structures and stores lab data only. It never calls AI, never diagnoses,
never produces clinical interpretation or patient-specific recommendations, and
never classifies inactive (non-Phase-1) parameters.

Transaction: the pipeline owns its transaction and commits on success /
rolls back on failure. No business logic lives in the SQLAlchemy models.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.alias_engine import AliasEngine
from app.domain.reference_resolver import ReferenceResolver
from app.domain.rule_engine import RuleEngine
from app.domain.trend_engine import TrendEngine
from app.domain.enums import AnalysisLevel, ResultStatus, TrendStatus
from app.infrastructure.database.models.analysis_run import AnalysisRun
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.repositories.analysis_run_repository import (
    AnalysisRunRepository,
)
from app.infrastructure.database.repositories.clinical_parameter_repository import (
    ClinicalParameterRepository,
)
from app.infrastructure.database.repositories.lab_report_repository import (
    LabReportRepository,
)
from app.infrastructure.database.repositories.lab_result_repository import (
    LabResultRepository,
)
from app.schemas.analysis import (
    ReferenceResolutionRequest,
)
from app.schemas.lab_analysis import (
    AnalysisCounts,
    AnalysisPipelineResult,
    MockLabReportInput,
    RawLabValue,
    StructuredLabResultOutput,
)
from app.schemas.rule_engine import RuleEvaluationInput
from app.schemas.trend import TrendComparisonInput

_REASON_UNMAPPED = "Parameter could not be mapped."
_REASON_RESOLVED_MISSING = "Resolved parameter record was not found."
_REASON_INACTIVE = "Parameter is not active in Phase 1."
_DAYS_PER_YEAR = 365.25


class AnalysisPipeline:
    def __init__(
        self,
        session: AsyncSession,
        *,
        alias_engine: AliasEngine,
        reference_resolver: ReferenceResolver,
        rule_engine: RuleEngine,
        trend_engine: TrendEngine,
        lab_report_repository: LabReportRepository,
        lab_result_repository: LabResultRepository,
        analysis_run_repository: AnalysisRunRepository,
        parameter_repository: ClinicalParameterRepository,
    ) -> None:
        self._session = session
        self._alias = alias_engine
        self._reference = reference_resolver
        self._rules = rule_engine
        self._trend = trend_engine
        self._reports = lab_report_repository
        self._results = lab_result_repository
        self._runs = analysis_run_repository
        self._parameters = parameter_repository

    async def run(self, payload: MockLabReportInput) -> AnalysisPipelineResult:
        try:
            return await self._run(payload)
        except Exception:
            await self._session.rollback()
            raise

    # ------------------------------------------------------------------
    async def _run(self, payload: MockLabReportInput) -> AnalysisPipelineResult:
        now = datetime.now(timezone.utc)

        # 0) Patient must exist before any analysis begins.
        patient = await self._session.get(Patient, payload.patient_id)
        if patient is None:
            raise ValueError("Patient not found.")

        # 1) LabReport ---------------------------------------------------
        report = LabReport(
            patient_id=payload.patient_id,
            uploaded_by_user_id=payload.uploaded_by_user_id,
            source_type="mock_json",
            file_name=payload.file_name,
            report_date=payload.report_date,
            raw_payload=payload.model_dump(mode="json"),
            status="received",
        )
        self._reports.create(report)
        await self._session.flush()

        # 2) AnalysisRun -------------------------------------------------
        run = AnalysisRun(
            patient_id=payload.patient_id,
            lab_report_id=report.id,
            status="running",
            started_at=now,
        )
        self._runs.create(run)
        await self._session.flush()

        # 3) Process each raw value -------------------------------------
        results: list[LabResult] = []
        for raw in payload.values:
            result = await self._process_value(
                raw, report=report, run=run, patient=patient
            )
            self._results.create(result)
            await self._session.flush()  # populate id for output
            results.append(result)

        # 4) Counts ------------------------------------------------------
        counts = self._count(results)
        self._runs.update_counts(
            run,
            total=counts.total,
            normal=counts.normal,
            low=counts.low,
            high=counts.high,
            needs_review=counts.needs_review,
            unknown=counts.unknown,
        )

        # 5) Complete ----------------------------------------------------
        self._runs.mark_completed(run)
        report.status = "analyzed"

        # 6) Commit (pipeline owns the transaction) ----------------------
        await self._session.commit()

        # 7) Result ------------------------------------------------------
        return AnalysisPipelineResult(
            analysis_run_id=run.id,
            lab_report_id=report.id,
            patient_id=payload.patient_id,
            results=[self._to_output(r) for r in results],
            counts=counts,
        )

    # ------------------------------------------------------------------
    async def _process_value(
        self,
        raw: RawLabValue,
        *,
        report: LabReport,
        run: AnalysisRun,
        patient: Patient,
    ) -> LabResult:
        # Effective measurement date, used consistently everywhere below.
        # The original extracted date is preserved only in metadata_json.
        measured_at = raw.measured_at or report.report_date

        alias = await self._alias.resolve(raw.raw_parameter_name)

        # (b) Alias cannot resolve -> UNKNOWN, no further engines.
        if not alias.is_resolved or alias.canonical_parameter_id is None:
            return self._passive_result(
                raw, report, run,
                measured_at=measured_at,
                reason=_REASON_UNMAPPED,
                parameter_id=None,
                parameter_code=None,
                canonical_name=None,
                alias_confidence=alias.confidence,
            )

        # (c) Load the canonical parameter.
        parameter = await self._parameters.get_by_id(alias.canonical_parameter_id)
        if parameter is None:
            return self._passive_result(
                raw, report, run,
                measured_at=measured_at,
                reason=_REASON_RESOLVED_MISSING,
                parameter_id=None,
                parameter_code=alias.parameter_code,
                canonical_name=alias.canonical_name,
                alias_confidence=alias.confidence,
            )

        # (d) Inactive / passive parameter -> store, do not classify.
        if not parameter.active_phase1 or parameter.analysis_level == AnalysisLevel.L0:
            return self._passive_result(
                raw, report, run,
                measured_at=measured_at,
                reason=_REASON_INACTIVE,
                parameter_id=parameter.id,
                parameter_code=parameter.parameter_code,
                canonical_name=parameter.canonical_name,
                alias_confidence=alias.confidence,
            )

        # (e) Active -> reference, rule, trend.
        reference = await self._reference.resolve(
            ReferenceResolutionRequest(
                canonical_parameter_id=parameter.id,
                extracted_reference_min=raw.extracted_reference_min,
                extracted_reference_max=raw.extracted_reference_max,
                extracted_unit=raw.extracted_unit,
                patient_age=self._age_years(patient, measured_at),
                patient_sex=patient.sex,
                pregnancy_status=patient.is_pregnant,
            )
        )

        rule = self._rules.evaluate(
            RuleEvaluationInput(
                parameter_id=parameter.id,
                parameter_code=parameter.parameter_code,
                raw_value=raw.raw_value,
                normalized_value=raw.normalized_value,
                unit=raw.unit or reference.unit,
                reference_min=reference.reference_min,
                reference_max=reference.reference_max,
                reference_source=reference.reference_source,
                reference_needs_review=reference.needs_review,
                alias_needs_review=alias.needs_review,
            )
        )

        previous = await self._results.latest_previous_result(
            patient_id=report.patient_id,
            parameter_id=parameter.id,
            before_date=measured_at,
        )
        trend = self._trend.compare(
            TrendComparisonInput(
                parameter_id=parameter.id,
                parameter_code=parameter.parameter_code,
                current_value=raw.normalized_value,
                previous_value=previous.normalized_value if previous else None,
                current_date=measured_at,
                previous_date=previous.measured_at if previous else None,
            )
        )

        return LabResult(
            patient_id=report.patient_id,
            lab_report_id=report.id,
            analysis_run_id=run.id,
            parameter_id=parameter.id,
            raw_parameter_name=raw.raw_parameter_name,
            parameter_code=parameter.parameter_code,
            canonical_name=parameter.canonical_name,
            raw_value=raw.raw_value,
            normalized_value=raw.normalized_value,
            unit=raw.unit or reference.unit,
            reference_min=reference.reference_min,
            reference_max=reference.reference_max,
            reference_source=reference.reference_source,
            result_status=rule.status,
            trend_status=trend.trend_status,
            previous_value=trend.previous_value,
            absolute_difference=trend.absolute_difference,
            percentage_difference=trend.percentage_difference,
            time_difference_days=trend.time_difference_days,
            alias_confidence=alias.confidence,
            reference_confidence=reference.confidence,
            classification_confidence=rule.confidence,
            trend_confidence=trend.confidence,
            needs_review=rule.needs_review,
            reason=rule.reason,
            rule_applied=rule.rule_applied,
            measured_at=measured_at,
            metadata_json={
                "alias_method": alias.match_method.value,
                "reference_strategy": reference.resolved_from.value,
                "reference_reason": reference.reason,
                "trend_reason": trend.reason,
                "extracted_measured_at": raw.measured_at.isoformat() if raw.measured_at else None,
            },
        )

    # ------------------------------------------------------------------
    def _passive_result(
        self,
        raw: RawLabValue,
        report: LabReport,
        run: AnalysisRun,
        *,
        measured_at: date | None,
        reason: str,
        parameter_id: uuid.UUID | None,
        parameter_code: str | None,
        canonical_name: str | None,
        alias_confidence: float,
    ) -> LabResult:
        """Store a value without classification (unknown/inactive)."""
        return LabResult(
            patient_id=report.patient_id,
            lab_report_id=report.id,
            analysis_run_id=run.id,
            parameter_id=parameter_id,
            raw_parameter_name=raw.raw_parameter_name,
            parameter_code=parameter_code,
            canonical_name=canonical_name,
            raw_value=raw.raw_value,
            normalized_value=raw.normalized_value,
            unit=raw.unit,
            reference_min=None,
            reference_max=None,
            reference_source=None,
            result_status=ResultStatus.UNKNOWN,
            trend_status=TrendStatus.NO_PREVIOUS_RESULT,
            previous_value=None,
            absolute_difference=None,
            percentage_difference=None,
            time_difference_days=None,
            alias_confidence=alias_confidence,
            reference_confidence=0.0,
            classification_confidence=0.0,
            trend_confidence=0.0,
            needs_review=True,
            reason=reason,
            rule_applied=None,
            measured_at=measured_at,
            metadata_json={
                "passive": True,
                "extracted_measured_at": raw.measured_at.isoformat() if raw.measured_at else None,
            },
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _age_years(patient: Patient, at_date: date | None) -> float | None:
        if patient.date_of_birth is None:
            return None
        reference_date = at_date or date.today()
        delta_days = (reference_date - patient.date_of_birth).days
        if delta_days < 0:
            return None
        return delta_days / _DAYS_PER_YEAR

    @staticmethod
    def _count(results: list[LabResult]) -> AnalysisCounts:
        total = len(results)
        normal = sum(1 for r in results if r.result_status == ResultStatus.NORMAL)
        low = sum(1 for r in results if r.result_status == ResultStatus.LOW)
        high = sum(1 for r in results if r.result_status == ResultStatus.HIGH)
        unknown = sum(1 for r in results if r.result_status == ResultStatus.UNKNOWN)
        needs_review = sum(
            1
            for r in results
            if r.needs_review or r.result_status == ResultStatus.NEEDS_REVIEW
        )
        return AnalysisCounts(
            total=total,
            normal=normal,
            low=low,
            high=high,
            needs_review=needs_review,
            unknown=unknown,
        )

    @staticmethod
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
