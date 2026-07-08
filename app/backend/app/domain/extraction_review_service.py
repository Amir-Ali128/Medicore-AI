"""ExtractionReviewService.

Persists Claude-extracted lab values as reviewable records, allows editing, and —
only after approval — runs the existing deterministic AnalysisPipeline. It never
diagnoses, never generates clinical hypotheses, never calls the clinical
hypothesis service, and never commits (the route owns the transaction).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.domain.analysis_pipeline import AnalysisPipeline
from app.domain.claude_lab_extraction_service import (
    ClaudeLabExtractionService,
)
from app.infrastructure.database.models.extracted_lab_value import ExtractedLabValue
from app.infrastructure.database.models.extraction_job import ExtractionJob
from app.infrastructure.database.repositories.extracted_lab_value_repository import (
    ExtractedLabValueRepository,
)
from app.infrastructure.database.repositories.extraction_job_repository import (
    ExtractionJobRepository,
)
from app.schemas.extraction_review import (
    ExtractedLabValueUpdate,
    ExtractionJobApproveRequest,
)
from app.schemas.lab_analysis import (
    AnalysisPipelineResult,
    MockLabReportInput,
    RawLabValue,
)

_STATUS_PENDING = "pending_review"
_STATUS_ANALYZED = "analyzed"
_STATUS_REJECTED = "rejected"
_STATUS_APPROVED = "approved"
_STATUS_EDITED = "edited"


class ExtractionReviewService:
    def __init__(
        self,
        extraction_service: ClaudeLabExtractionService,
        analysis_pipeline: AnalysisPipeline,
        extraction_job_repository: ExtractionJobRepository,
        extracted_value_repository: ExtractedLabValueRepository,
    ) -> None:
        self._extraction = extraction_service
        self._pipeline = analysis_pipeline
        self._jobs = extraction_job_repository
        self._values = extracted_value_repository

    # 1) ----------------------------------------------------------------
    async def create_job_from_file(
        self,
        file_bytes: bytes,
        file_name: str | None,
        content_type: str | None,
        patient_id: uuid.UUID | None,
        uploaded_by_user_id: uuid.UUID | None,
    ) -> ExtractionJob:
        extraction = await self._extraction.extract_from_bytes(
            file_bytes, file_name, content_type
        )

        warnings = list(extraction.warnings)
        if not extraction.values:
            warnings.append("No extracted lab values found.")

        job = ExtractionJob(
            patient_id=patient_id,
            uploaded_by_user_id=uploaded_by_user_id,
            source_file_name=file_name,
            source_content_type=content_type,
            status=_STATUS_PENDING,
            overall_needs_review=extraction.overall_needs_review,
            extraction_confidence=extraction.extraction_confidence,
            warnings_json=warnings,
            metadata_json={},
        )
        self._jobs.create(job)
        await self._jobs.flush()  # populate job.id

        rows = [
            ExtractedLabValue(
                extraction_job_id=job.id,
                raw_parameter_name=item.raw_parameter_name,
                raw_value=item.raw_value,
                normalized_value=item.normalized_value,
                unit=item.unit,
                extracted_reference_min=item.extracted_reference_min,
                extracted_reference_max=item.extracted_reference_max,
                extracted_unit=item.extracted_unit,
                measured_at=item.measured_at,
                needs_review=item.needs_review,
                extraction_note=item.extraction_note,
                review_status=_STATUS_PENDING if item.needs_review else _STATUS_APPROVED,
            )
            for item in extraction.values
        ]
        if rows:
            self._values.create_many(rows)
        await self._values.flush()

        return job

    # 2) ----------------------------------------------------------------
    async def update_extracted_value(
        self,
        extracted_value_id: uuid.UUID,
        payload: ExtractedLabValueUpdate,
    ) -> ExtractedLabValue:
        value = await self._values.get_by_id(extracted_value_id)
        if value is None:
            raise ValueError("Extracted lab value not found.")

        changes: dict[str, Any] = payload.model_dump(exclude_unset=True)

        edited_by = changes.get("edited_by_user_id")
        if edited_by is not None:
            changes["edited_at"] = datetime.now(timezone.utc)
            if "review_status" not in changes:
                changes["review_status"] = _STATUS_EDITED

        self._values.update(value, changes)
        await self._values.flush()
        return value

    # 3) ----------------------------------------------------------------
    async def approve_and_analyze(
        self,
        extraction_job_id: uuid.UUID,
        payload: ExtractionJobApproveRequest,
    ) -> tuple[ExtractionJob, AnalysisPipelineResult]:
        job = await self._jobs.get_by_id(extraction_job_id)
        if job is None:
            raise ValueError("Extraction job not found.")

        values = list(await self._values.list_for_job(extraction_job_id))
        if not values:
            raise ValueError("Extraction job has no values to analyze.")

        usable = [v for v in values if v.review_status != _STATUS_REJECTED]
        if not usable:
            raise ValueError("Extraction job has no approved values to analyze.")

        report_input = MockLabReportInput(
            patient_id=payload.patient_id,
            uploaded_by_user_id=payload.uploaded_by_user_id or job.uploaded_by_user_id,
            file_name=job.source_file_name,
            report_date=payload.report_date,
            values=[
                RawLabValue(
                    raw_parameter_name=v.raw_parameter_name or "",
                    raw_value=v.raw_value,
                    normalized_value=v.normalized_value,
                    unit=v.unit,
                    extracted_reference_min=v.extracted_reference_min,
                    extracted_reference_max=v.extracted_reference_max,
                    extracted_unit=v.extracted_unit,
                    measured_at=v.measured_at,
                )
                for v in usable
            ],
        )

        analysis = await self._pipeline.run(report_input)

        job.status = _STATUS_ANALYZED
        job.patient_id = payload.patient_id
        job.reviewed_by_user_id = payload.reviewed_by_user_id
        job.reviewed_at = datetime.now(timezone.utc)
        job.lab_report_id = analysis.lab_report_id
        job.analysis_run_id = analysis.analysis_run_id
        await self._jobs.flush()

        return job, analysis
