"""Clinical copilot routes.

Generates doctor-reviewable clinical hypotheses from deterministic case evidence.
The traditional endpoint is analysis-run scoped; a patient-scoped source-only path
supports clinical-only or ultrasound-only cases without fabricating lab records.
No final diagnosis, treatment advice, medication order or automatic test order is
produced by these endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import ClaudeClinicalHypothesisServiceDep, SessionDep
from app.domain.source_only_case_evaluation import generate_source_only_case
from app.infrastructure.database.models.patient import Patient
from app.schemas.clinical_copilot import (
    ClinicalHypothesisGenerationRequest,
    ClinicalHypothesisGenerationResult,
)

router = APIRouter(tags=["clinical-copilot"])

_ANALYSIS_RUN_NOT_FOUND = "Analysis run not found."


@router.post(
    "/analysis-runs/{analysis_run_id}/clinical-hypotheses/generate",
    response_model=ClinicalHypothesisGenerationResult,
    status_code=status.HTTP_201_CREATED,
)
async def generate_clinical_hypotheses(
    analysis_run_id: uuid.UUID,
    payload: ClinicalHypothesisGenerationRequest,
    session: SessionDep,
    service: ClaudeClinicalHypothesisServiceDep,
) -> ClinicalHypothesisGenerationResult:
    try:
        result = await service.generate_for_analysis_run(analysis_run_id, payload)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        message = str(exc)
        if message == _ANALYSIS_RUN_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=message
            ) from None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=message
        ) from None
    except Exception:
        await session.rollback()
        raise

    return result


@router.post(
    "/clinical-evaluations/source-only/generate",
    response_model=ClinicalHypothesisGenerationResult,
    status_code=status.HTTP_201_CREATED,
)
async def generate_source_only_clinical_evaluation(
    payload: ClinicalHypothesisGenerationRequest,
    session: SessionDep,
    service: ClaudeClinicalHypothesisServiceDep,
) -> ClinicalHypothesisGenerationResult:
    """Evaluate one or two available non-lab sources for an existing patient."""

    if payload.patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="patient_id is required for source-only evaluation.",
        )

    patient = await session.get(Patient, payload.patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found.",
        )

    try:
        result = await generate_source_only_case(service, payload.patient_id, payload)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return result
