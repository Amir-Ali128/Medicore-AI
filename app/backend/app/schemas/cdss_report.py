"""Schemas for the simplified physician-facing MediCore CDSS flow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.extraction import LabExtractionResult


class ClinicalContext(BaseModel):
    """Clinician-supplied context accompanying laboratory and imaging reports."""

    model_config = ConfigDict(extra="forbid")

    patient_reference: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = None

    chief_complaint: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    vital_signs: dict[str, str | int | float | None] = Field(default_factory=dict)
    additional_notes: str | None = None


class DifferentialDiagnosisItem(BaseModel):
    """Non-final differential item intended for physician review."""

    condition: str
    rationale: str
    likelihood_label: Literal["low", "moderate", "high", "uncertain"] = "uncertain"


class CDSSReport(BaseModel):
    """Structured physician-facing clinical decision-support output."""

    report_title: str = "KLİNİK KARAR DESTEK RAPORU"
    clinical_information: str
    laboratory_findings: list[str] = Field(default_factory=list)
    imaging_findings: str
    clinical_assessment: str
    differential_diagnosis: list[DifferentialDiagnosisItem] = Field(default_factory=list)
    attention_points: list[str] = Field(default_factory=list)
    recommended_clinical_evaluation: list[str] = Field(default_factory=list)
    conclusion: str
    limitations: list[str] = Field(default_factory=list)
    physician_review_required: bool = True
    disclaimer: str = (
        "Bu çıktı klinik karar desteği içindir; kesin tanı ve tedavi kararı "
        "yetkili hekim tarafından verilmelidir."
    )


class CDSSReportGenerationResult(BaseModel):
    """Complete result of a simplified MediCore CDSS evaluation."""

    generated_at: datetime
    clinical_context: ClinicalContext
    lab_extraction: LabExtractionResult
    imaging_report_text: str
    report: CDSSReport
    warnings: list[str] = Field(default_factory=list)
