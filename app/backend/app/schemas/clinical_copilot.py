"""Pydantic v2 schemas for the Claude clinical hypothesis copilot.

All outputs are doctor-reviewable hypotheses. They are never final diagnoses
and never treatment advice.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.clinical_hypothesis import ClinicalHypothesisResponse


class ClinicalHypothesisEvidenceDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    lab_result_id: uuid.UUID | None = None
    parameter_code: str | None = None
    parameter_name: str | None = None
    value: str | None = None
    unit: str | None = None
    result_status: str | None = None
    note: str | None = None


class ClinicalHypothesisDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    summary: str
    hypothesis_type: str | None = None
    confidence: float | None = None
    severity: str | None = None
    suggested_doctor_action: str | None = None
    evidence_json: list[ClinicalHypothesisEvidenceDraft] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)


class ClinicalHypothesisGenerationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: uuid.UUID | None = None
    max_hypotheses: int = 5
    include_needs_review_only: bool = False
    metadata_json: dict = Field(default_factory=dict)


class ClinicalHypothesisGenerationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_run_id: uuid.UUID
    patient_id: uuid.UUID | None = None
    generated_count: int = 0
    hypotheses: list[ClinicalHypothesisResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
