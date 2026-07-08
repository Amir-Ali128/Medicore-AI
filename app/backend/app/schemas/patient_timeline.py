"""Pydantic v2 schemas for the patient timeline.

Operational audit-trail events only — no diagnosis, no interpretation, no
treatment advice. String event types/statuses (no enums).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PatientTimelineEventCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: uuid.UUID
    event_type: str
    status: str = "info"
    title: str
    description: str | None = None
    occurred_at: datetime | None = None
    source: str = "system"
    source_entity_type: str | None = None
    source_entity_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    lab_report_id: uuid.UUID | None = None
    analysis_run_id: uuid.UUID | None = None
    clinical_hypothesis_id: uuid.UUID | None = None
    doctor_review_id: uuid.UUID | None = None
    extraction_job_id: uuid.UUID | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PatientTimelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    event_type: str
    status: str
    title: str
    description: str | None
    occurred_at: datetime
    source: str
    source_entity_type: str | None
    source_entity_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    lab_report_id: uuid.UUID | None
    analysis_run_id: uuid.UUID | None
    clinical_hypothesis_id: uuid.UUID | None
    doctor_review_id: uuid.UUID | None
    extraction_job_id: uuid.UUID | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PatientTimelineListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: uuid.UUID
    events: list[PatientTimelineEventResponse] = Field(default_factory=list)
    count: int = 0
