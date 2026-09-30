"""API routes for the simplified MediCore v1 case flow."""

from fastapi import APIRouter

from app.domain.simple_case import normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest, SimpleCaseResponse


router = APIRouter(prefix="/simple-case", tags=["simple-case"])


@router.post("/normalize", response_model=SimpleCaseResponse)
async def normalize_case(payload: SimpleCaseRequest) -> SimpleCaseResponse:
    """Normalize clinical + lab + report data without diagnostic classification."""

    return normalize_simple_case(payload)
