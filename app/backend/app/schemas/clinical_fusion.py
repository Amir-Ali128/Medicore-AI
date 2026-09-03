"""Schemas for MediCore Clinical Fusion Brain v1.

The fusion endpoint ranks physician-reviewable possibilities from normalized evidence.
Scores are evidence-compatibility scores, never estimated disease probabilities or
final diagnoses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FusionSourceType = Literal[
    "clinical",
    "history",
    "vital",
    "laboratory",
    "imaging",
    "ai_detector",
    "ai_reader",
    "other",
]
FusionPolarity = Literal["support", "oppose", "uncertain"]
FusionSeverity = Literal["low", "moderate", "high", "critical"]
FusionLevel = Literal["very_low", "low", "moderate", "high", "very_high"]


class ClinicalFusionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=240)
    category: str | None = Field(default=None, max_length=120)

    @field_validator("code", "display_name", "category", mode="before")
    @classmethod
    def clean_text(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = " ".join(value.split())
            return cleaned or None
        return value


class ClinicalFusionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    finding_code: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=500)
    source_type: FusionSourceType
    source_name: str = Field(min_length=1, max_length=160)
    dependency_group: str | None = Field(default=None, max_length=160)
    polarity: FusionPolarity
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    severity: FusionSeverity = "moderate"
    hypothesis_codes: list[str] = Field(default_factory=list, max_length=32)
    observed_at: datetime | None = None
    location: dict[str, Any] | None = None
    value: str | float | int | None = None
    unit: str | None = Field(default=None, max_length=80)
    model_id: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "id",
        "finding_code",
        "label",
        "source_name",
        "dependency_group",
        "unit",
        "model_id",
        mode="before",
    )
    @classmethod
    def clean_text(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = " ".join(value.split())
            return cleaned or None
        return value

    @field_validator("hypothesis_codes")
    @classmethod
    def unique_hypothesis_codes(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = " ".join(str(value).split())
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned[:32]


class ClinicalFusionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: list[ClinicalFusionCandidate] = Field(min_length=1, max_length=40)
    evidence: list[ClinicalFusionEvidence] = Field(default_factory=list, max_length=500)
    source_availability: dict[str, bool] = Field(default_factory=dict)
    language: str = Field(default="tr", min_length=2, max_length=16)

    @field_validator("candidates")
    @classmethod
    def unique_candidate_codes(
        cls, values: list[ClinicalFusionCandidate]
    ) -> list[ClinicalFusionCandidate]:
        seen: set[str] = set()
        for item in values:
            key = item.code.casefold()
            if key in seen:
                raise ValueError(f"Duplicate fusion candidate code: {item.code}")
            seen.add(key)
        return values

    @field_validator("evidence")
    @classmethod
    def unique_evidence_ids(
        cls, values: list[ClinicalFusionEvidence]
    ) -> list[ClinicalFusionEvidence]:
        seen: set[str] = set()
        for item in values:
            key = item.id.casefold()
            if key in seen:
                raise ValueError(f"Duplicate fusion evidence id: {item.id}")
            seen.add(key)
        return values


class ClinicalFusionDisagreement(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal[
        "cross_source_conflict",
        "ai_model_disagreement",
        "ai_vs_primary_evidence",
    ]
    hypothesis_code: str
    evidence_ids: list[str]
    detail: str


class ClinicalFusionCandidateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    display_name: str
    category: str | None = None
    compatibility_score: float = Field(ge=0.0, le=100.0)
    compatibility_level: FusionLevel
    level_label: str
    score_type: Literal["deterministic_evidence_compatibility"] = (
        "deterministic_evidence_compatibility"
    )
    estimated_probability: None = None
    support_strength: float = Field(ge=0.0)
    oppose_strength: float = Field(ge=0.0)
    support_group_count: int = Field(ge=0)
    oppose_group_count: int = Field(ge=0)
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str]
    uncertain_evidence_ids: list[str]
    supporting_source_types: list[str]
    limitations: list[str]
    summary: str
    requires_physician_review: Literal[True] = True


class ClinicalFusionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: Literal["clinical-fusion-v1"] = "clinical-fusion-v1"
    candidates: list[ClinicalFusionCandidateResult]
    critical_signal_ids: list[str]
    disagreements: list[ClinicalFusionDisagreement]
    core_source_coverage: dict[str, bool]
    core_source_count: int = Field(ge=0, le=3)
    core_source_total: Literal[3] = 3
    data_completeness_percent: int = Field(ge=0, le=100)
    ai_reader_available: bool
    unmapped_hypothesis_codes: list[str]
    warnings: list[str]
    requires_physician_review: Literal[True] = True
    disclaimer: str
