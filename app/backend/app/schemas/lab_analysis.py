"""DTOs for structured clinical intake and lab-analysis output.

Pydantic v2 models keep the deterministic lab pipeline separate from clinical
interpretation. Clinical intake fields are stored as structured context and may
be passed to the physician-review copilot, but they never change a lab result
status directly.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import ResultStatus, TrendStatus


class _NormalizedInputModel(BaseModel):
    """Strip optional text while preserving numeric values."""

    model_config = ConfigDict(frozen=True)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


# --------------------------------------------------------------------------
# Input: deterministic lab values
# --------------------------------------------------------------------------
class RawLabValue(_NormalizedInputModel):
    raw_parameter_name: str
    raw_value: str | None = None
    normalized_value: Decimal | None = None
    unit: str | None = None
    extracted_reference_min: Decimal | None = None
    extracted_reference_max: Decimal | None = None
    extracted_unit: str | None = None
    measured_at: date | None = None


# --------------------------------------------------------------------------
# Input: clinical intake
# --------------------------------------------------------------------------
class PatientInformationInput(_NormalizedInputModel):
    full_name: str | None = Field(default=None, max_length=200)
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = Field(default=None, max_length=32)
    height_cm: Decimal | None = Field(default=None, ge=30, le=260)
    weight_kg: Decimal | None = Field(default=None, ge=1, le=600)


class PresentingComplaintInput(_NormalizedInputModel):
    reason_for_visit: str | None = Field(default=None, max_length=2000)
    chief_complaint: str | None = Field(default=None, max_length=2000)
    complaint_duration: str | None = Field(default=None, max_length=500)
    severity_score: int | None = Field(default=None, ge=0, le=10)
    associated_symptoms: str | None = Field(default=None, max_length=5000)


class ClinicalHistoryInput(_NormalizedInputModel):
    history_of_present_illness: str | None = Field(default=None, max_length=8000)
    current_medical_conditions: str | None = Field(default=None, max_length=5000)
    past_medical_history: str | None = Field(default=None, max_length=5000)
    family_history: str | None = Field(default=None, max_length=5000)
    medications: str | None = Field(default=None, max_length=5000)
    allergies: str | None = Field(default=None, max_length=3000)
    tobacco_alcohol: str | None = Field(default=None, max_length=3000)
    past_surgeries: str | None = Field(default=None, max_length=5000)


class PhysicalExamInput(_NormalizedInputModel):
    blood_pressure_systolic: int | None = Field(default=None, ge=40, le=300)
    blood_pressure_diastolic: int | None = Field(default=None, ge=20, le=200)
    pulse_bpm: int | None = Field(default=None, ge=20, le=300)
    temperature_c: Decimal | None = Field(default=None, ge=30, le=45)
    respiratory_rate: int | None = Field(default=None, ge=4, le=80)
    oxygen_saturation_percent: Decimal | None = Field(default=None, ge=0, le=100)
    examination_findings: str | None = Field(default=None, max_length=10000)


class ImagingResultsInput(_NormalizedInputModel):
    xray: str | None = Field(default=None, max_length=10000)
    ultrasound: str | None = Field(default=None, max_length=10000)
    ct: str | None = Field(default=None, max_length=10000)
    mri: str | None = Field(default=None, max_length=10000)
    pet_ct: str | None = Field(default=None, max_length=10000)
    pathology: str | None = Field(default=None, max_length=10000)


ClinicalAttachmentCategory = Literal[
    "laboratory",
    "xray",
    "ultrasound",
    "ct",
    "mri",
    "pet_ct",
    "pathology",
    "dicom",
    "other",
]


class ClinicalAttachmentInput(_NormalizedInputModel):
    file_name: str = Field(max_length=512)
    category: ClinicalAttachmentCategory = "other"
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(ge=0, le=100 * 1024 * 1024)
    last_modified_ms: int | None = Field(default=None, ge=0)


class MockLabReportInput(_NormalizedInputModel):
    patient_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None = None
    file_name: str | None = Field(default=None, max_length=512)
    report_date: date | None = None

    patient_information: PatientInformationInput = Field(
        default_factory=PatientInformationInput
    )
    presenting_complaint: PresentingComplaintInput = Field(
        default_factory=PresentingComplaintInput
    )
    clinical_history_details: ClinicalHistoryInput = Field(
        default_factory=ClinicalHistoryInput
    )
    physical_exam: PhysicalExamInput = Field(default_factory=PhysicalExamInput)
    imaging_results: ImagingResultsInput = Field(default_factory=ImagingResultsInput)
    attachments: list[ClinicalAttachmentInput] = Field(default_factory=list)

    # Backward-compatible fields used by older clients.
    chief_complaint: str | None = Field(default=None, max_length=2000)
    clinical_history: str | None = Field(default=None, max_length=5000)

    values: list[RawLabValue] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Output: patient metadata
# --------------------------------------------------------------------------
class PatientMetadataOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_name: str | None = None
    age: int | None = None
    sex: str | None = None
    birth_date: date | None = None
    height_cm: Decimal | None = None
    weight_kg: Decimal | None = None


# --------------------------------------------------------------------------
# Output: structured analysis
# --------------------------------------------------------------------------
class StructuredLabResultOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    lab_result_id: uuid.UUID | None = None
    raw_parameter_name: str
    parameter_id: uuid.UUID | None = None
    parameter_code: str | None = None
    canonical_name: str | None = None
    normalized_value: Decimal | None = None
    unit: str | None = None
    reference_min: Decimal | None = None
    reference_max: Decimal | None = None
    result_status: ResultStatus = ResultStatus.UNKNOWN
    trend_status: TrendStatus = TrendStatus.NO_PREVIOUS_RESULT
    needs_review: bool = True
    reason: str | None = None
    alias_confidence: float = 0.0
    reference_confidence: float = 0.0
    classification_confidence: float = 0.0
    trend_confidence: float = 0.0


class AnalysisCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int = 0
    normal: int = 0
    low: int = 0
    high: int = 0
    needs_review: int = 0
    unknown: int = 0


class AnalysisPipelineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_run_id: uuid.UUID
    lab_report_id: uuid.UUID
    patient_id: uuid.UUID
    patient: PatientMetadataOutput = Field(default_factory=PatientMetadataOutput)
    results: list[StructuredLabResultOutput] = Field(default_factory=list)
    counts: AnalysisCounts = Field(default_factory=AnalysisCounts)
