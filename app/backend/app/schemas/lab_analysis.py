"""DTOs for mock lab extraction input and structured analysis output.

Pydantic v2. Statuses use the approved domain enums (no duplicate enums here).
These schemas only carry structured data — no diagnosis or interpretation.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import ResultStatus, TrendStatus


# --------------------------------------------------------------------------
# Input (mock extraction)
# --------------------------------------------------------------------------
class RawLabValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_parameter_name: str
    raw_value: str | None = None
    normalized_value: Decimal | None = None
    unit: str | None = None
    extracted_reference_min: Decimal | None = None
    extracted_reference_max: Decimal | None = None
    extracted_unit: str | None = None
    measured_at: date | None = None


class MockLabReportInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None = None
    file_name: str | None = None
    report_date: date | None = None
    chief_complaint: str | None = Field(default=None, max_length=2000)
    clinical_history: str | None = Field(default=None, max_length=5000)
    values: list[RawLabValue] = Field(default_factory=list)

    @field_validator("chief_complaint", "clinical_history", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


# --------------------------------------------------------------------------
# Output (patient metadata extracted from PDF)
# --------------------------------------------------------------------------
class PatientMetadataOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_name: str | None = None
    age: int | None = None
    sex: str | None = None
    birth_date: date | None = None


# --------------------------------------------------------------------------
# Output (structured analysis)
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

    # Extracted from the uploaded PDF when available.
    # These fields are for UI display only.
    patient: PatientMetadataOutput = Field(default_factory=PatientMetadataOutput)

    results: list[StructuredLabResultOutput] = Field(default_factory=list)
    counts: AnalysisCounts = Field(default_factory=AnalysisCounts)
