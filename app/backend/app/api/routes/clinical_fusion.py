"""Deterministic Clinical Fusion Brain endpoint.

The endpoint is stateless and does not persist a diagnosis. It ranks supplied
physician-reviewable possibilities from normalized evidence and returns conflicts,
coverage, and limitations for downstream UI/review workflows.
"""

from fastapi import APIRouter

from app.domain.clinical_fusion_brain import evaluate_clinical_fusion
from app.schemas.clinical_fusion import ClinicalFusionRequest, ClinicalFusionResult

router = APIRouter(tags=["clinical-fusion"])


@router.post(
    "/clinical-fusion/evaluate",
    response_model=ClinicalFusionResult,
)
async def evaluate_clinical_fusion_endpoint(
    payload: ClinicalFusionRequest,
) -> ClinicalFusionResult:
    return evaluate_clinical_fusion(payload)
