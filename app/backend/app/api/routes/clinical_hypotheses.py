"""Clinical hypothesis routes.

A clinical hypothesis is a system/AI-suggested possibility that always requires
doctor review. These endpoints never diagnose and never produce treatment advice.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import ClinicalHypothesisRepositoryDep, SessionDep
from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
from app.schemas.clinical_hypothesis import (
    ClinicalHypothesisCreate,
    ClinicalHypothesisResponse,
)

router = APIRouter(tags=["clinical-hypotheses"])


@router.post(
    "/clinical-hypotheses",
    response_model=ClinicalHypothesisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_clinical_hypothesis(
    payload: ClinicalHypothesisCreate,
    session: SessionDep,
    repository: ClinicalHypothesisRepositoryDep,
) -> ClinicalHypothesisResponse:
    hypothesis = ClinicalHypothesis(
        patient_id=payload.patient_id,
        lab_report_id=payload.lab_report_id,
        analysis_run_id=payload.analysis_run_id,
        title=payload.title,
        summary=payload.summary,
        hypothesis_type=payload.hypothesis_type,
        confidence=payload.confidence,
        severity=payload.severity,
        status="pending_review",
        source=payload.source,
        evidence_json=[item.model_dump() for item in payload.evidence_json],
        needs_doctor_review=True,
        metadata_json=dict(payload.metadata_json),
    )
    try:
        repository.create(hypothesis)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return ClinicalHypothesisResponse.model_validate(hypothesis)


@router.get(
    "/clinical-hypotheses/status/pending",
    response_model=list[ClinicalHypothesisResponse],
)
async def list_pending_clinical_hypotheses(
    repository: ClinicalHypothesisRepositoryDep,
) -> list[ClinicalHypothesisResponse]:
    return list(await repository.list_pending())


@router.get(
    "/clinical-hypotheses/{clinical_hypothesis_id}",
    response_model=ClinicalHypothesisResponse,
)
async def get_clinical_hypothesis(
    clinical_hypothesis_id: uuid.UUID,
    repository: ClinicalHypothesisRepositoryDep,
) -> ClinicalHypothesisResponse:
    hypothesis = await repository.get_by_id(clinical_hypothesis_id)
    if hypothesis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinical hypothesis not found.",
        )
    return hypothesis


@router.get(
    "/patients/{patient_id}/clinical-hypotheses",
    response_model=list[ClinicalHypothesisResponse],
)
async def list_clinical_hypotheses_for_patient(
    patient_id: uuid.UUID,
    repository: ClinicalHypothesisRepositoryDep,
) -> list[ClinicalHypothesisResponse]:
    return list(await repository.list_for_patient(patient_id))


@router.get(
    "/analysis-runs/{analysis_run_id}/clinical-hypotheses",
    response_model=list[ClinicalHypothesisResponse],
)
async def list_clinical_hypotheses_for_analysis_run(
    analysis_run_id: uuid.UUID,
    repository: ClinicalHypothesisRepositoryDep,
) -> list[ClinicalHypothesisResponse]:
    return list(await repository.list_for_analysis_run(analysis_run_id))
