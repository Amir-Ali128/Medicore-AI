"""Pydantic v2 schemas for doctor reviews.

Uses the approved domain `ReviewAction` enum. A doctor review records a
physician's action on a clinical hypothesis; it carries no diagnosis or
treatment advice.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ReviewAction
from app.schemas.clinical_hypothesis import ClinicalHypothesisResponse


class DoctorReviewCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    doctor_id: uuid.UUID
    action: ReviewAction
    doctor_note: str | None = None
    edited_title: str | None = None
    edited_summary: str | None = None
    requested_tests_json: list[str] | None = None
    specialist_referral: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class DoctorReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinical_hypothesis_id: uuid.UUID
    doctor_id: uuid.UUID
    action: ReviewAction
    doctor_note: str | None
    edited_title: str | None
    edited_summary: str | None
    requested_tests_json: list[str] | None
    specialist_referral: str | None
    reviewed_at: datetime
    created_at: datetime
    updated_at: datetime


class DoctorReviewActionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    clinical_hypothesis: ClinicalHypothesisResponse
    doctor_review: DoctorReviewResponse
