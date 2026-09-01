"""Dedicated route for the PDF-first laboratory parser.

A unique path avoids any ambiguity with the legacy /lab-analysis/upload route.
"""

from fastapi import APIRouter, File, UploadFile, status

from app.api.dependencies import SessionDep
from app.api.routes.lab_pdf_direct_upload import analyze_uploaded_pdf_direct
from app.schemas.lab_analysis import AnalysisPipelineResult

router = APIRouter(prefix="/lab-analysis", tags=["lab-analysis"])


@router.post(
    "/upload-direct",
    response_model=AnalysisPipelineResult,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_uploaded_pdf_direct_alias(
    session: SessionDep,
    file: UploadFile = File(...),
) -> AnalysisPipelineResult:
    return await analyze_uploaded_pdf_direct(session=session, file=file)
