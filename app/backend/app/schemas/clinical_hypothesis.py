"""Pydantic v2 schemas for clinical hypotheses.

A clinical hypothesis is a system/AI-suggested possibility that always requires
doctor review — never a final diagnosis and never treatment advice.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    parameter_code: str | None = None
    parameter_name: str | None = None
    value: str | None = None
    unit: str | None = None
    result_status: str | None = None
    note: str | None = None


class ClinicalHypothesisCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: uuid.UUID
    lab_report_id: uuid.UUID | None = None
    analysis_run_id: uuid.UUID | None = None
    title: str
    summary: str
    hypothesis_type: str | None = None
    confidence: float | None = None
    severity: str | None = None
    source: str = "system"
    evidence_json: list[EvidenceItem] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)


class ClinicalHypothesisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    lab_report_id: uuid.UUID | None
    analysis_run_id: uuid.UUID | None
    title: str
    summary: str
    hypothesis_type: str | None
    confidence: float | None
    severity: str | None
    status: str
    source: str
    evidence_json: list[EvidenceItem]
    needs_doctor_review: bool
    reviewed_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
