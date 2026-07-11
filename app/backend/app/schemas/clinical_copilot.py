"""Pydantic v2 schemas for the Claude clinical evaluation copilot.

All outputs are physician-reviewable possibilities. They are never final diagnoses,
automatic test orders, or treatment advice.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)

from app.schemas.clinical_hypothesis import ClinicalHypothesisResponse


class ClinicalHypothesisEvidenceDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    lab_result_id: uuid.UUID | None = None
    parameter_code: str | None = None
    parameter_name: str | None = None
    value: str | None = None
    unit: str | None = None
    result_status: str | None = None
    trend_status: str | None = None
    note: str | None = None


class SuggestedDiagnosticTestDraft(BaseModel):
    """A physician-reviewable diagnostic test suggestion, never an automatic order."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    rationale: str | None = Field(default=None, max_length=600)
    priority: Literal["routine", "soon", "urgent"] | None = None

    @field_validator("name", "rationale", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ClinicalHypothesisDraft(BaseModel):
    """Validated Claude draft before it is persisted for physician review."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    title: str
    summary: str
    hypothesis_type: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    severity: str | None = None
    evidence: list[ClinicalHypothesisEvidenceDraft] = Field(
        default_factory=list,
        validation_alias=AliasChoices("evidence", "evidence_json"),
    )
    limitations: list[str] = Field(default_factory=list)
    possible_conditions: list[str] = Field(default_factory=list)
    recommended_laboratory_tests: list[SuggestedDiagnosticTestDraft] = Field(
        default_factory=list
    )
    recommended_imaging_tests: list[SuggestedDiagnosticTestDraft] = Field(
        default_factory=list
    )
    suggested_doctor_actions: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "suggested_doctor_actions",
            "suggested_doctor_action",
        ),
    )

    @field_validator(
        "suggested_doctor_actions",
        "possible_conditions",
        "limitations",
        mode="before",
    )
    @classmethod
    def normalize_string_list(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("possible_conditions", "limitations")
    @classmethod
    def clean_string_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned[:10]


class ClinicalHypothesisGenerationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    patient_id: uuid.UUID | None = None
    max_hypotheses: int = Field(default=5, ge=1, le=10)
    include_normal_results: bool = False
    include_needs_review_only: bool = False
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    language: str = Field(default="tr", min_length=2, max_length=16)
    metadata_json: dict = Field(default_factory=dict)


class ClinicalHypothesisGenerationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_run_id: uuid.UUID
    lab_report_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None
    created_hypotheses: list[ClinicalHypothesisResponse] = Field(default_factory=list)
    drafts_count: int = 0
    created_count: int = 0
    warnings: list[str] = Field(default_factory=list)

    # Backward-compatible response fields for any older frontend caller.
    @computed_field
    @property
    def hypotheses(self) -> list[ClinicalHypothesisResponse]:
        return self.created_hypotheses

    @computed_field
    @property
    def generated_count(self) -> int:
        return self.created_count
