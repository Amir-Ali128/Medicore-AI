"""Case-level input/output contracts for Clinical Fusion Brain v2.

The v2 adapter accepts structured case signals from MediCore subsystems and converts
those signals into the existing deterministic Clinical Fusion v1 evidence contract.
It never invents disease associations: every signal must explicitly name the
candidate hypothesis codes it supports, opposes, or leaves uncertain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.clinical_fusion import (
    ClinicalFusionCandidate,
    ClinicalFusionEvidence,
    ClinicalFusionResult,
    FusionPolarity,
    FusionSeverity,
)

ClinicalSignalKind = Literal["symptom", "exam", "history", "vital"]
ImagingSignalKind = Literal["primary", "detector"]


class _SignalBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    finding_code: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=500)
    polarity: FusionPolarity = "support"
    hypothesis_codes: list[str] = Field(default_factory=list, max_length=32)
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    severity: FusionSeverity = "moderate"
    observed_at: datetime | None = None
    value: str | float | int | None = None
    unit: str | None = Field(default=None, max_length=80)
    location: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "finding_code", "label", "unit", mode="before")
    @classmethod
    def clean_text(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = " ".join(value.split())
            return cleaned or None
        return value

    @field_validator("hypothesis_codes")
    @classmethod
    def clean_hypotheses(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for raw in values:
            item = " ".join(str(raw).split())
            key = item.casefold()
            if item and key not in seen:
                output.append(item)
                seen.add(key)
        return output[:32]


class ClinicalCaseSignal(_SignalBase):
    kind: ClinicalSignalKind
    source_name: str = Field(default="clinical-intake", min_length=1, max_length=160)


class LaboratoryCaseSignal(_SignalBase):
    report_id: str | None = Field(default=None, max_length=160)
    source_name: str = Field(default="laboratory", min_length=1, max_length=160)


class ImagingCaseSignal(_SignalBase):
    study_id: str = Field(min_length=1, max_length=160)
    kind: ImagingSignalKind = "primary"
    source_name: str = Field(default="radiology", min_length=1, max_length=160)
    model_id: str | None = Field(default=None, max_length=160)


class AIReaderCaseSignal(_SignalBase):
    study_id: str = Field(min_length=1, max_length=160)
    provider: str = Field(min_length=1, max_length=160)
    model_id: str | None = Field(default=None, max_length=160)


class OnnxFindingScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=160)
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    above_threshold: bool

    @field_validator("label", mode="before")
    @classmethod
    def clean_label(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())
        return value


class OnnxCaseRun(BaseModel):
    """One X-Ray ONNX run adapted from ``OnnxInferenceEngine`` output.

    ``hypothesis_map`` is deliberately explicit. The adapter does not infer a disease
    association from a model label. A below-threshold finding becomes ``uncertain``
    rather than automatically opposing a diagnosis.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=160)
    study_id: str = Field(min_length=1, max_length=160)
    model_id: str = Field(min_length=1, max_length=160)
    model_version: str | None = Field(default=None, max_length=80)
    findings: list[OnnxFindingScore] = Field(default_factory=list, max_length=256)
    hypothesis_map: dict[str, list[str]] = Field(default_factory=dict)
    location_by_label: dict[str, dict[str, Any]] = Field(default_factory=dict)
    severity_by_label: dict[str, FusionSeverity] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_label_maps(self) -> "OnnxCaseRun":
        labels = {item.label.casefold() for item in self.findings}
        for mapping_name, mapping in (
            ("hypothesis_map", self.hypothesis_map),
            ("location_by_label", self.location_by_label),
            ("severity_by_label", self.severity_by_label),
        ):
            unknown = [key for key in mapping if key.casefold() not in labels]
            if unknown:
                raise ValueError(
                    f"{mapping_name} contains labels absent from findings: {unknown[:5]}"
                )
        return self


class ClinicalFusionCaseRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1, max_length=160)
    candidates: list[ClinicalFusionCandidate] = Field(min_length=1, max_length=40)
    clinical_signals: list[ClinicalCaseSignal] = Field(default_factory=list, max_length=200)
    laboratory_signals: list[LaboratoryCaseSignal] = Field(default_factory=list, max_length=300)
    imaging_signals: list[ImagingCaseSignal] = Field(default_factory=list, max_length=300)
    ai_reader_signals: list[AIReaderCaseSignal] = Field(default_factory=list, max_length=400)
    onnx_runs: list[OnnxCaseRun] = Field(default_factory=list, max_length=32)
    source_availability: dict[str, bool] = Field(default_factory=dict)
    language: str = Field(default="tr", min_length=2, max_length=16)

    @field_validator("candidates")
    @classmethod
    def unique_candidate_codes(
        cls,
        values: list[ClinicalFusionCandidate],
    ) -> list[ClinicalFusionCandidate]:
        seen: set[str] = set()
        for item in values:
            key = item.code.casefold()
            if key in seen:
                raise ValueError(f"Duplicate fusion candidate code: {item.code}")
            seen.add(key)
        return values

    @model_validator(mode="after")
    def unique_signal_ids(self) -> "ClinicalFusionCaseRequest":
        ids: list[str] = []
        ids.extend(item.id for item in self.clinical_signals)
        ids.extend(item.id for item in self.laboratory_signals)
        ids.extend(item.id for item in self.imaging_signals)
        ids.extend(item.id for item in self.ai_reader_signals)
        # ONNX evidence IDs are generated deterministically from run_id + finding label;
        # duplicate run IDs would otherwise collide.
        ids.extend(f"onnx-run:{item.run_id}" for item in self.onnx_runs)
        seen: set[str] = set()
        duplicates: list[str] = []
        for raw in ids:
            key = raw.casefold()
            if key in seen and raw not in duplicates:
                duplicates.append(raw)
            seen.add(key)
        if duplicates:
            raise ValueError(f"Duplicate case signal/run IDs: {duplicates[:5]}")
        return self


class ClinicalFusionGraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["candidate", "evidence", "dependency_group"]
    label: str
    source_type: str | None = None
    polarity: FusionPolarity | None = None


class ClinicalFusionGraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    relation: Literal["supports", "opposes", "uncertain_for", "member_of"]


class ClinicalFusionCaseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: Literal["clinical-fusion-case-v1"] = "clinical-fusion-case-v1"
    fusion: ClinicalFusionResult
    normalized_evidence: list[ClinicalFusionEvidence]
    graph_nodes: list[ClinicalFusionGraphNode]
    graph_edges: list[ClinicalFusionGraphEdge]
    source_evidence_counts: dict[str, int]
    review_priority: Literal["routine", "priority", "critical"]
    needs_conflict_review: bool
    adapter_warnings: list[str]
    requires_physician_review: Literal[True] = True
