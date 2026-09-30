"""Simplified MediCore case contract.

The v1 simplification intentionally models only three inputs:
clinical context, laboratory results, and medical reports.

Important: this contract does not classify laboratory values as normal/abnormal,
high/low, or into disease classes. Reference ranges are source data copied from
the uploaded laboratory report.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SexValue = Literal["female", "male", "other", "unknown"]


class ClinicalContext(BaseModel):
    age: int | None = Field(default=None, ge=0, le=130)
    sex: SexValue = "unknown"
    complaints: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    notes: str | None = None


class LabReferenceRange(BaseModel):
    """A reference range exactly as represented by the source report.

    Numeric bounds are optional because many reports use textual references
    such as "negative", "< 5", or age/sex-specific tables.
    """

    text: str
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    age_min: int | None = Field(default=None, ge=0, le=130)
    age_max: int | None = Field(default=None, ge=0, le=130)
    sex: SexValue | None = None

    @model_validator(mode="after")
    def validate_age_bounds(self) -> "LabReferenceRange":
        if (
            self.age_min is not None
            and self.age_max is not None
            and self.age_min > self.age_max
        ):
            raise ValueError("age_min cannot be greater than age_max")
        return self


class LabResultInput(BaseModel):
    test_name: str = Field(min_length=1, max_length=256)
    value: str | float | int | None = None
    unit: str | None = None
    measured_at: date | datetime | None = None
    source_reference: str | None = None
    source_references: list[LabReferenceRange] = Field(default_factory=list)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class LabResultOutput(BaseModel):
    test_name: str
    value: str | float | int | None
    unit: str | None
    measured_at: date | datetime | None
    reference_text: str | None
    reference_source: Literal["report", "report_age_sex_match", "missing"]
    reference_details: LabReferenceRange | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class MedicalReportInput(BaseModel):
    """Generic report input for ECG, echo, US, CT, X-ray, MRI, etc."""

    report_type: str = Field(min_length=1, max_length=128)
    report_date: date | datetime | None = None
    body_region: str | None = None
    findings: str | None = None
    impression: str | None = None
    raw_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimpleCaseRequest(BaseModel):
    clinical: ClinicalContext = Field(default_factory=ClinicalContext)
    labs: list[LabResultInput] = Field(default_factory=list)
    reports: list[MedicalReportInput] = Field(default_factory=list)


class SimpleCaseResponse(BaseModel):
    contract_version: Literal["medicore-simple-case-v1"] = "medicore-simple-case-v1"
    clinical: ClinicalContext
    labs: list[LabResultOutput]
    reports: list[MedicalReportInput]
    warnings: list[str] = Field(default_factory=list)


class CaseAIInterpretationResponse(BaseModel):
    clinical_summary: str
    integrated_findings: list[str] = Field(default_factory=list)
    correlations: list[str] = Field(default_factory=list)
    attention_points: list[str] = Field(default_factory=list)
    missing_or_conflicting_data: list[str] = Field(default_factory=list)
    clinician_conclusion: str
    limitations: list[str] = Field(default_factory=list)
    model: str
