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

_COMPACT_TYPE = "compact_risk_summary"
_COMPACT_SOURCE = "claude_compact_risk_summary"
_SOURCE_ONLY_SCOPE = "source_only"


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


@router.delete(
    "/analysis-runs/{analysis_run_id}/clinical-hypotheses/compact",
)
async def delete_compact_clinical_hypotheses_for_analysis_run(
    analysis_run_id: uuid.UUID,
    session: SessionDep,
    repository: ClinicalHypothesisRepositoryDep,
) -> dict[str, int]:
    """Delete every compact AI evaluation for one analysis run.

    Older builds could create duplicate compact evaluations. Deleting the current
    AI output therefore removes all compact snapshots for this run so a hidden old
    duplicate cannot reappear after refresh.
    """

    hypotheses = list(await repository.list_for_analysis_run(analysis_run_id))
    compact = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.hypothesis_type == _COMPACT_TYPE
        or hypothesis.source == _COMPACT_SOURCE
    ]

    try:
        for hypothesis in compact:
            await session.delete(hypothesis)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return {"deleted_count": len(compact)}


@router.delete(
    "/patients/{patient_id}/clinical-hypotheses/compact/source-only",
)
async def delete_source_only_compact_hypotheses_for_patient(
    patient_id: uuid.UUID,
    session: SessionDep,
    repository: ClinicalHypothesisRepositoryDep,
) -> dict[str, int]:
    """Delete compact evaluations created without a laboratory analysis run."""

    hypotheses = list(await repository.list_for_patient(patient_id))
    compact = []
    for hypothesis in hypotheses:
        metadata = hypothesis.metadata_json if isinstance(hypothesis.metadata_json, dict) else {}
        if hypothesis.analysis_run_id is not None:
            continue
        if metadata.get("source_evaluation_scope") != _SOURCE_ONLY_SCOPE:
            continue
        if (
            hypothesis.hypothesis_type == _COMPACT_TYPE
            or hypothesis.source == _COMPACT_SOURCE
        ):
            compact.append(hypothesis)

    try:
        for hypothesis in compact:
            await session.delete(hypothesis)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return {"deleted_count": len(compact)}
