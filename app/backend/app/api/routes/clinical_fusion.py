"""Deterministic Clinical Fusion Brain endpoints.

The endpoints are stateless and do not persist a diagnosis. The legacy endpoint
accepts already-normalized evidence. The case-level v2 endpoint accepts structured
signals from MediCore subsystems, normalizes them deterministically, and returns an
auditable evidence graph plus the existing fusion ranking.
"""

from fastapi import APIRouter

from app.domain.clinical_fusion_brain import evaluate_clinical_fusion
from app.domain.clinical_fusion_case_adapter import evaluate_clinical_case_fusion
from app.schemas.clinical_fusion import ClinicalFusionRequest, ClinicalFusionResult
from app.schemas.clinical_fusion_case import (
    ClinicalFusionCaseRequest,
    ClinicalFusionCaseResult,
)

router = APIRouter(tags=["clinical-fusion"])


@router.post(
    "/clinical-fusion/evaluate",
    response_model=ClinicalFusionResult,
)
async def evaluate_clinical_fusion_endpoint(
    payload: ClinicalFusionRequest,
) -> ClinicalFusionResult:
    return evaluate_clinical_fusion(payload)


@router.post(
    "/clinical-fusion/evaluate-case",
    response_model=ClinicalFusionCaseResult,
)
async def evaluate_clinical_case_fusion_endpoint(
    payload: ClinicalFusionCaseRequest,
) -> ClinicalFusionCaseResult:
    return evaluate_clinical_case_fusion(payload)
