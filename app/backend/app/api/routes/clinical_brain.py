"""Backend-owned clinical brain endpoint."""

from fastapi import APIRouter

from app.domain.clinical_brain import evaluate_clinical_brain
from app.schemas.clinical_brain import ClinicalBrainRequest, ClinicalBrainResult

router = APIRouter(tags=["clinical-brain"])


@router.post("/clinical-brain/evaluate", response_model=ClinicalBrainResult)
async def evaluate_clinical_brain_endpoint(payload: ClinicalBrainRequest) -> ClinicalBrainResult:
    return evaluate_clinical_brain(payload)
