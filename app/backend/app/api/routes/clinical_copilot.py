"""Clinical copilot routes.

Generates doctor-reviewable clinical hypotheses (Module J) from an analysis
run's deterministic lab results. No final diagnosis, no treatment advice, no
patient-facing interpretation. There is no patient-facing endpoint here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import ClaudeClinicalHypothesisServiceDep, SessionDep
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
