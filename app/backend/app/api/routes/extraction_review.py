"""Extraction review routes.

Stores Claude-extracted lab values as reviewable records, allows editing, and —
only after approval — runs the deterministic AnalysisPipeline. No diagnosis, no
clinical hypotheses, no treatment advice.
"""

from __future__ import annotations

import mimetypes
import uuid
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import (
    ExtractedLabValueRepositoryDep,
    ExtractionJobRepositoryDep,
    ExtractionReviewServiceDep,
    SessionDep,
)
from app.domain.claude_lab_extraction_service import (
    SUPPORTED_CONTENT_TYPES,
)
from app.infrastructure.database.models.extracted_lab_value import ExtractedLabValue
from app.infrastructure.database.models.extraction_job import ExtractionJob
from app.schemas.extraction_review import (
    ExtractedLabValueResponse,
    ExtractedLabValueUpdate,
    ExtractionJobAnalyzeResponse,
    ExtractionJobApproveRequest,
    ExtractionJobCreateResponse,
)

router = APIRouter(prefix="/extraction-review", tags=["extraction-review"])

_JOB_NOT_FOUND = "Extraction job not found."
_VALUE_NOT_FOUND = "Extracted lab value not found."
_PATIENT_NOT_FOUND = "Patient not found."


def _resolve_content_type(file: UploadFile) -> str | None:
    content_type = (file.content_type or "").lower() or None
    if content_type in SUPPORTED_CONTENT_TYPES:
        return content_type
    guessed, _ = mimetypes.guess_type(file.filename or "")
    return guessed or content_type


def _job_response(
    job: ExtractionJob, values: list[ExtractedLabValue]
) -> ExtractionJobCreateResponse:
    return ExtractionJobCreateResponse(
        id=job.id,
        patient_id=job.patient_id,
        uploaded_by_user_id=job.uploaded_by_user_id,
        source_file_name=job.source_file_name,
        source_content_type=job.source_content_type,
        status=job.status,
        overall_needs_review=job.overall_needs_review,
        extraction_confidence=job.extraction_confidence,
        warnings_json=list(job.warnings_json or []),
        created_at=job.created_at,
        updated_at=job.updated_at,
        values=[ExtractedLabValueResponse.model_validate(v) for v in values],
    )


@router.post(
    "/jobs/from-file",
    response_model=ExtractionJobCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_job_from_file(
    session: SessionDep,
    service: ExtractionReviewServiceDep,
    value_repository: ExtractedLabValueRepositoryDep,
    file: UploadFile = File(...),
    patient_id: uuid.UUID | None = Form(default=None),
    uploaded_by_user_id: uuid.UUID | None = Form(default=None),
) -> ExtractionJobCreateResponse:
    data = await file.read()
    content_type = _resolve_content_type(file)
    try:
        job = await service.create_job_from_file(
            data, file.filename, content_type, patient_id, uploaded_by_user_id
        )
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None
    except Exception:
        await session.rollback()
        raise

    values = list(await value_repository.list_for_job(job.id))
    return _job_response(job, values)


@router.get("/jobs/status/pending", response_model=list[ExtractionJobCreateResponse])
async def list_pending_jobs(
    job_repository: ExtractionJobRepositoryDep,
    value_repository: ExtractedLabValueRepositoryDep,
) -> list[ExtractionJobCreateResponse]:
    jobs = await job_repository.list_pending()
    return [
        _job_response(job, list(await value_repository.list_for_job(job.id)))
        for job in jobs
    ]


@router.get("/jobs/{extraction_job_id}", response_model=ExtractionJobCreateResponse)
async def get_job(
    extraction_job_id: uuid.UUID,
    job_repository: ExtractionJobRepositoryDep,
    value_repository: ExtractedLabValueRepositoryDep,
) -> ExtractionJobCreateResponse:
    job = await job_repository.get_by_id(extraction_job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_JOB_NOT_FOUND
        )
    values = list(await value_repository.list_for_job(job.id))
    return _job_response(job, values)


@router.get(
    "/patients/{patient_id}/jobs",
    response_model=list[ExtractionJobCreateResponse],
)
async def list_jobs_for_patient(
    patient_id: uuid.UUID,
    job_repository: ExtractionJobRepositoryDep,
    value_repository: ExtractedLabValueRepositoryDep,
) -> list[ExtractionJobCreateResponse]:
    jobs = await job_repository.list_for_patient(patient_id)
    return [
        _job_response(job, list(await value_repository.list_for_job(job.id)))
        for job in jobs
    ]


@router.patch("/values/{extracted_value_id}", response_model=ExtractedLabValueResponse)
async def update_extracted_value(
    extracted_value_id: uuid.UUID,
    payload: ExtractedLabValueUpdate,
    session: SessionDep,
    service: ExtractionReviewServiceDep,
) -> ExtractedLabValueResponse:
    try:
        value = await service.update_extracted_value(extracted_value_id, payload)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    except Exception:
        await session.rollback()
        raise
    return ExtractedLabValueResponse.model_validate(value)


@router.post(
    "/jobs/{extraction_job_id}/approve-and-analyze",
    response_model=ExtractionJobAnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def approve_and_analyze(
    extraction_job_id: uuid.UUID,
    payload: ExtractionJobApproveRequest,
    session: SessionDep,
    service: ExtractionReviewServiceDep,
    value_repository: ExtractedLabValueRepositoryDep,
) -> ExtractionJobAnalyzeResponse:
    try:
        job, analysis = await service.approve_and_analyze(extraction_job_id, payload)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        message = str(exc)
        if message in (_JOB_NOT_FOUND, _PATIENT_NOT_FOUND):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=message
            ) from None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=message
        ) from None
    except Exception:
        await session.rollback()
        raise

    values = list(await value_repository.list_for_job(job.id))
    return ExtractionJobAnalyzeResponse(
        extraction_job=_job_response(job, values), analysis=analysis
    )
