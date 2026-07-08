"""FastAPI dependency wiring.

Provides one request-scoped async session, plus repository and service providers
built on top of it. FastAPI caches `get_session` per request, so every repository
and service in a request shares the same session instance.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

from app.domain.alias_engine import AliasEngine
from app.domain.analysis_pipeline import AnalysisPipeline
from app.domain.claude_clinical_hypothesis_service import (
    ClaudeClinicalHypothesisService,
)
from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
from app.domain.doctor_review_service import DoctorReviewService
from app.domain.extraction_review_service import ExtractionReviewService
from app.domain.patient_timeline_service import PatientTimelineService
from app.domain.reference_resolver import ReferenceResolver
from app.domain.rule_engine import RuleEngine
from app.domain.trend_engine import TrendEngine

from app.infrastructure.database.repositories.analysis_run_repository import (
    AnalysisRunRepository,
)
from app.infrastructure.database.repositories.clinical_parameter_repository import (
    ClinicalParameterRepository,
)
from app.infrastructure.database.repositories.clinical_hypothesis_repository import (
    ClinicalHypothesisRepository,
)
from app.infrastructure.database.repositories.doctor_review_repository import (
    DoctorReviewRepository,
)
from app.infrastructure.database.repositories.extracted_lab_value_repository import (
    ExtractedLabValueRepository,
)
from app.infrastructure.database.repositories.extraction_job_repository import (
    ExtractionJobRepository,
)
from app.infrastructure.database.repositories.lab_report_repository import (
    LabReportRepository,
)
from app.infrastructure.database.repositories.lab_result_repository import (
    LabResultRepository,
)
from app.infrastructure.database.repositories.parameter_alias_repository import (
    ParameterAliasRepository,
)
from app.infrastructure.database.repositories.patient_timeline_repository import (
    PatientTimelineRepository,
)
from app.infrastructure.database.repositories.reference_range_repository import (
    ReferenceRangeRepository,
)
from app.infrastructure.database.session import AsyncSessionFactory


# --- Session --------------------------------------------------------------
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# --- Repositories ---------------------------------------------------------
def get_clinical_parameter_repository(
    session: SessionDep,
) -> ClinicalParameterRepository:
    return ClinicalParameterRepository(session)


def get_parameter_alias_repository(
    session: SessionDep,
) -> ParameterAliasRepository:
    return ParameterAliasRepository(session)


def get_reference_range_repository(
    session: SessionDep,
) -> ReferenceRangeRepository:
    return ReferenceRangeRepository(session)


def get_lab_report_repository(session: SessionDep) -> LabReportRepository:
    return LabReportRepository(session)


def get_lab_result_repository(session: SessionDep) -> LabResultRepository:
    return LabResultRepository(session)


def get_analysis_run_repository(session: SessionDep) -> AnalysisRunRepository:
    return AnalysisRunRepository(session)


def get_clinical_hypothesis_repository(
    session: SessionDep,
) -> ClinicalHypothesisRepository:
    return ClinicalHypothesisRepository(session)


def get_doctor_review_repository(session: SessionDep) -> DoctorReviewRepository:
    return DoctorReviewRepository(session)


def get_extraction_job_repository(session: SessionDep) -> ExtractionJobRepository:
    return ExtractionJobRepository(session)


def get_extracted_lab_value_repository(
    session: SessionDep,
) -> ExtractedLabValueRepository:
    return ExtractedLabValueRepository(session)


def get_patient_timeline_repository(
    session: SessionDep,
) -> PatientTimelineRepository:
    return PatientTimelineRepository(session)


ClinicalParameterRepositoryDep = Annotated[
    ClinicalParameterRepository,
    Depends(get_clinical_parameter_repository),
]

ParameterAliasRepositoryDep = Annotated[
    ParameterAliasRepository,
    Depends(get_parameter_alias_repository),
]

ReferenceRangeRepositoryDep = Annotated[
    ReferenceRangeRepository,
    Depends(get_reference_range_repository),
]

LabReportRepositoryDep = Annotated[
    LabReportRepository,
    Depends(get_lab_report_repository),
]

LabResultRepositoryDep = Annotated[
    LabResultRepository,
    Depends(get_lab_result_repository),
]

AnalysisRunRepositoryDep = Annotated[
    AnalysisRunRepository,
    Depends(get_analysis_run_repository),
]

ClinicalHypothesisRepositoryDep = Annotated[
    ClinicalHypothesisRepository,
    Depends(get_clinical_hypothesis_repository),
]

DoctorReviewRepositoryDep = Annotated[
    DoctorReviewRepository,
    Depends(get_doctor_review_repository),
]

ExtractionJobRepositoryDep = Annotated[
    ExtractionJobRepository,
    Depends(get_extraction_job_repository),
]

ExtractedLabValueRepositoryDep = Annotated[
    ExtractedLabValueRepository,
    Depends(get_extracted_lab_value_repository),
]

PatientTimelineRepositoryDep = Annotated[
    PatientTimelineRepository,
    Depends(get_patient_timeline_repository),
]


# --- Core services --------------------------------------------------------
def get_alias_engine(
    parameter_repository: ClinicalParameterRepositoryDep,
    alias_repository: ParameterAliasRepositoryDep,
) -> AliasEngine:
    return AliasEngine(parameter_repository, alias_repository)


def get_reference_resolver(
    reference_range_repository: ReferenceRangeRepositoryDep,
    parameter_repository: ClinicalParameterRepositoryDep,
) -> ReferenceResolver:
    return ReferenceResolver(reference_range_repository, parameter_repository)


def get_rule_engine() -> RuleEngine:
    return RuleEngine()


def get_trend_engine() -> TrendEngine:
    return TrendEngine()


AliasEngineDep = Annotated[
    AliasEngine,
    Depends(get_alias_engine),
]

ReferenceResolverDep = Annotated[
    ReferenceResolver,
    Depends(get_reference_resolver),
]

RuleEngineDep = Annotated[
    RuleEngine,
    Depends(get_rule_engine),
]

TrendEngineDep = Annotated[
    TrendEngine,
    Depends(get_trend_engine),
]


def get_analysis_pipeline(
    session: SessionDep,
    alias_engine: AliasEngineDep,
    reference_resolver: ReferenceResolverDep,
    rule_engine: RuleEngineDep,
    trend_engine: TrendEngineDep,
    lab_report_repository: LabReportRepositoryDep,
    lab_result_repository: LabResultRepositoryDep,
    analysis_run_repository: AnalysisRunRepositoryDep,
    parameter_repository: ClinicalParameterRepositoryDep,
) -> AnalysisPipeline:
    return AnalysisPipeline(
        session,
        alias_engine=alias_engine,
        reference_resolver=reference_resolver,
        rule_engine=rule_engine,
        trend_engine=trend_engine,
        lab_report_repository=lab_report_repository,
        lab_result_repository=lab_result_repository,
        analysis_run_repository=analysis_run_repository,
        parameter_repository=parameter_repository,
    )


AnalysisPipelineDep = Annotated[
    AnalysisPipeline,
    Depends(get_analysis_pipeline),
]


# --- Module H: hypotheses & doctor review --------------------------------
def get_doctor_review_service(
    hypothesis_repository: ClinicalHypothesisRepositoryDep,
    review_repository: DoctorReviewRepositoryDep,
) -> DoctorReviewService:
    return DoctorReviewService(hypothesis_repository, review_repository)


DoctorReviewServiceDep = Annotated[
    DoctorReviewService,
    Depends(get_doctor_review_service),
]


# --- Module I: Claude lab extraction service -----------------------------
def get_claude_lab_extraction_service() -> ClaudeLabExtractionService:
    settings = get_settings()

    try:
        return ClaudeLabExtractionService(
            api_key=settings.anthropic_api_key,
            model=settings.claude_extraction_model,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Extraction service is not configured.",
        ) from None


ClaudeLabExtractionServiceDep = Annotated[
    ClaudeLabExtractionService,
    Depends(get_claude_lab_extraction_service),
]


# --- Module J: Claude clinical hypothesis copilot -------------------------
def get_claude_clinical_hypothesis_service(
    lab_result_repository: LabResultRepositoryDep,
    clinical_hypothesis_repository: ClinicalHypothesisRepositoryDep,
    analysis_run_repository: AnalysisRunRepositoryDep,
) -> ClaudeClinicalHypothesisService:
    settings = get_settings()

    try:
        return ClaudeClinicalHypothesisService(
            api_key=settings.anthropic_api_key,
            model=settings.claude_hypothesis_model,
            lab_result_repository=lab_result_repository,
            clinical_hypothesis_repository=clinical_hypothesis_repository,
            analysis_run_repository=analysis_run_repository,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clinical copilot service is not configured.",
        ) from None


ClaudeClinicalHypothesisServiceDep = Annotated[
    ClaudeClinicalHypothesisService,
    Depends(get_claude_clinical_hypothesis_service),
]


# --- Module K: extraction review -----------------------------------------
def get_extraction_review_service(
    extraction_service: ClaudeLabExtractionServiceDep,
    analysis_pipeline: AnalysisPipelineDep,
    extraction_job_repository: ExtractionJobRepositoryDep,
    extracted_value_repository: ExtractedLabValueRepositoryDep,
) -> ExtractionReviewService:
    return ExtractionReviewService(
        extraction_service,
        analysis_pipeline,
        extraction_job_repository,
        extracted_value_repository,
    )


ExtractionReviewServiceDep = Annotated[
    ExtractionReviewService,
    Depends(get_extraction_review_service),
]


# --- Module L: patient timeline ------------------------------------------
def get_patient_timeline_service(
    patient_timeline_repository: PatientTimelineRepositoryDep,
) -> PatientTimelineService:
    return PatientTimelineService(patient_timeline_repository)


PatientTimelineServiceDep = Annotated[
    PatientTimelineService,
    Depends(get_patient_timeline_service),
]
