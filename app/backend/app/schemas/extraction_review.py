"""Pydantic v2 schemas for extraction review.

Stores Claude-extracted lab values as reviewable records before deterministic
analysis. No diagnosis, no interpretation, no treatment advice. String statuses
only (no enums).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lab_analysis import AnalysisPipelineResult


class ExtractedLabValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    extraction_job_id: uuid.UUID
    raw_parameter_name: str | None
    raw_value: str | None
    normalized_value: Decimal | None
    unit: str | None
    extracted_reference_min: Decimal | None
    extracted_reference_max: Decimal | None
    extracted_unit: str | None
    measured_at: date | None
    needs_review: bool
    extraction_note: str | None
    review_status: str
    edited_by_user_id: uuid.UUID | None
    edited_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExtractionJobCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID | None
    uploaded_by_user_id: uuid.UUID | None
    source_file_name: str | None
    source_content_type: str | None
    status: str
    overall_needs_review: bool
    extraction_confidence: float | None
    warnings_json: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    values: list[ExtractedLabValueResponse] = Field(default_factory=list)


class ExtractedLabValueUpdate(BaseModel):
    raw_parameter_name: str | None = None
    raw_value: str | None = None
    normalized_value: Decimal | None = None
    unit: str | None = None
    extracted_reference_min: Decimal | None = None
    extracted_reference_max: Decimal | None = None
    extracted_unit: str | None = None
    measured_at: date | None = None
    needs_review: bool | None = None
    extraction_note: str | None = None
    review_status: str | None = None
    edited_by_user_id: uuid.UUID | None = None


class ExtractionJobApproveRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: uuid.UUID
    reviewed_by_user_id: uuid.UUID | None = None
    uploaded_by_user_id: uuid.UUID | None = None
    report_date: date | None = None


class ExtractionJobAnalyzeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    extraction_job: ExtractionJobCreateResponse
    analysis: AnalysisPipelineResult
