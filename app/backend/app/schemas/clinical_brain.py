"""Contracts for the backend-owned clinical brain.

The browser may render these values, but clinical interpretation, source selection,
summary construction, and compatibility scoring live in Python so there is one
server-side source of truth. Scores are evidence-compatibility scores, never disease
probabilities, and every output requires physician review.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lab_analysis import (
    ClinicalAttachmentInput,
    ClinicalHistoryInput,
    ImagingResultsInput,
    PatientInformationInput,
    PhysicalExamInput,
    PresentingComplaintInput,
    StructuredLabResultOutput,
)
from app.schemas.radiology_report import RadiologyReportResponse


class ClinicalBrainContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    patient_information: PatientInformationInput = Field(default_factory=PatientInformationInput)
    presenting_complaint: PresentingComplaintInput = Field(default_factory=PresentingComplaintInput)
    clinical_history_details: ClinicalHistoryInput = Field(default_factory=ClinicalHistoryInput)
    physical_exam: PhysicalExamInput = Field(default_factory=PhysicalExamInput)
    imaging_results: ImagingResultsInput = Field(default_factory=ImagingResultsInput)
    attachments: list[ClinicalAttachmentInput] = Field(default_factory=list, max_length=100)


class ClinicalBrainRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    clinical_context: ClinicalBrainContext | None = None
    lab_results: list[StructuredLabResultOutput] = Field(default_factory=list, max_length=1000)
    radiology_reports: list[RadiologyReportResponse] = Field(default_factory=list, max_length=500)
    language: str = Field(default="tr", min_length=2, max_length=16)


class ClinicalBrainSourceSummaries(BaseModel):
    model_config = ConfigDict(frozen=True)

    clinical: str
    laboratory: str
    ultrasound: str


class ClinicalBrainSourceAvailability(BaseModel):
    model_config = ConfigDict(frozen=True)

    clinical: bool
    laboratory: bool
    ultrasound: bool


class ClinicalBrainSourceDates(BaseModel):
    model_config = ConfigDict(frozen=True)

    laboratory: str | None = None
    ultrasound: str | None = None


class ClinicalBrainPerformedStudy(BaseModel):
    model_config = ConfigDict(frozen=True)

    canonical_code: str
    name: str
    date: str | None = None
    source_report_id: str


DoctorSignalSeverity = Literal["low", "moderate", "high"]


class DoctorInterpretationItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    system: str
    severity: DoctorSignalSeverity
    markers: list[str]
    interpretation: str
    clinical_context: str
    suggested_doctor_action: str


class DoctorInterpretationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    abnormal_count: int
    low_count: int
    high_count: int
    items: list[DoctorInterpretationItem]
    safety_note: str


CompatibilityLevel = Literal["very_low", "low", "moderate", "high", "very_high"]
CompatibilityDomain = Literal[
    "clinical_findings",
    "laboratory_findings",
    "imaging_findings",
    "cross_modal_consistency",
]


class CompatibilityEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    label: str
    domain: CompatibilityDomain
    points: int
    maximum_points: int
    matched: bool
    detail: str


class CompatibilityBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain: CompatibilityDomain
    label: str
    score: int
    maximum_score: int


class ClinicalCompatibilityScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    hypothesis_code: Literal["acute_calculous_cholecystitis"] = "acute_calculous_cholecystitis"
    display_name: Literal["Akut kalkülöz kolesistit"] = "Akut kalkülöz kolesistit"
    score: int
    maximum_score: Literal[100] = 100
    level: CompatibilityLevel
    level_label: str
    score_type: Literal["rule_based_evidence_compatibility"] = "rule_based_evidence_compatibility"
    estimated_probability: None = None
    data_completeness_percent: int
    breakdown: list[CompatibilityBreakdown]
    evidence: list[CompatibilityEvidence]
    supporting_evidence: list[CompatibilityEvidence]
    missing_data: list[str]
    requires_clinician_review: Literal[True] = True
    disclaimer: str


class ClinicalBrainResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_version: Literal["clinical-brain-v1"] = "clinical-brain-v1"
    source_summaries: ClinicalBrainSourceSummaries
    ai_source_summaries: ClinicalBrainSourceSummaries
    source_availability: ClinicalBrainSourceAvailability
    source_dates: ClinicalBrainSourceDates
    temporal_gap_days: int | None = None
    performed_studies: list[ClinicalBrainPerformedStudy]
    ultrasound_context_flags: list[str]
    selected_ultrasound_report_id: uuid.UUID | None = None
    doctor_interpretation: DoctorInterpretationSummary
    compatibility: ClinicalCompatibilityScore
    requires_physician_review: Literal[True] = True
    disclaimer: str
