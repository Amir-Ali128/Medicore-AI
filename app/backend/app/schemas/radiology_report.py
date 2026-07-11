"""Pydantic schemas for Phase 2 radiology and DXA report text analysis."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

DEMO_PATIENT_ID = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
DEMO_UPLOADED_BY_USER_ID = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")


class RadiologyFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    classification: str
    is_critical: bool = False
    matched_terms: list[str] = Field(default_factory=list)


class RadiologyMeasurement(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str
    unit: str
    context: str


class DexaMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    site: str
    bmd: float | None = None
    bmd_unit: str | None = None
    t_score: float | None = None
    z_score: float | None = None
    t_score_band: str | None = None
    z_score_band: str | None = None
    report_classification: str | None = None
    context: str


class RadiologyReportCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    patient_id: uuid.UUID = DEMO_PATIENT_ID
    uploaded_by_user_id: uuid.UUID | None = DEMO_UPLOADED_BY_USER_ID
    report_date: date | None = None
    modality: str | None = None
    body_part: str | None = None
    report_text: str = Field(min_length=10, max_length=250_000)
    file_name: str | None = Field(default=None, max_length=512)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("modality", "body_part")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
        return normalized or None


class RadiologyReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None
    source_type: str
    file_name: str | None
    report_date: date | None
    modality: str
    body_part: str
    original_text: str
    findings: list[RadiologyFinding] = Field(
        default_factory=list,
        validation_alias=AliasChoices("findings", "findings_json"),
    )
    measurements: list[RadiologyMeasurement] = Field(
        default_factory=list,
        validation_alias=AliasChoices("measurements", "measurements_json"),
    )
    dexa_metrics: list[DexaMetric] = Field(
        default_factory=list,
        validation_alias=AliasChoices("dexa_metrics", "dexa_metrics_json"),
    )
    critical_findings: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("critical_findings", "critical_findings_json"),
    )
    impression: str | None
    summary: str
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
