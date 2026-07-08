"""Doctor review routes.

A doctor review applies a physician's action to a clinical hypothesis. Doctor
action is required before any hypothesis is approved/rejected/edited/etc. These
endpoints never diagnose and never produce treatment advice.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import DoctorReviewRepositoryDep, DoctorReviewServiceDep, SessionDep
from app.schemas.clinical_hypothesis import ClinicalHypothesisResponse
from app.schemas.doctor_review import (
    DoctorReviewActionResponse,
    DoctorReviewCreate,
    DoctorReviewResponse,
)

router = APIRouter(tags=["doctor-reviews"])

_HYPOTHESIS_NOT_FOUND = "Clinical hypothesis not found."


@router.post(
    "/clinical-hypotheses/{clinical_hypothesis_id}/reviews",
    response_model=DoctorReviewActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_doctor_review(
    clinical_hypothesis_id: uuid.UUID,
    payload: DoctorReviewCreate,
    session: SessionDep,
    service: DoctorReviewServiceDep,
) -> DoctorReviewActionResponse:
    try:
        hypothesis, review = await service.apply_review(clinical_hypothesis_id, payload)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        if str(exc) == _HYPOTHESIS_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None
    except Exception:
        await session.rollback()
        raise

    return DoctorReviewActionResponse(
        clinical_hypothesis=ClinicalHypothesisResponse.model_validate(hypothesis),
        doctor_review=DoctorReviewResponse.model_validate(review),
    )


@router.get(
    "/clinical-hypotheses/{clinical_hypothesis_id}/reviews",
    response_model=list[DoctorReviewResponse],
)
async def list_doctor_reviews(
    clinical_hypothesis_id: uuid.UUID,
    repository: DoctorReviewRepositoryDep,
) -> list[DoctorReviewResponse]:
    return list(await repository.list_for_hypothesis(clinical_hypothesis_id))
