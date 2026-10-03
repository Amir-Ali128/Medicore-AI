"""Read-only projections referencing existing patient, lab and report records."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.simple_case import ClinicalContext, VitalSigns


class TimelineLabValue(BaseModel):
    id: str
    test_name: str
    value: str | float | int | None = None
    unit: str | None = None
    reference_text: str | None = None


class PatientHealthTimelineEntry(BaseModel):
    id: str
    patient_id: UUID
    kind: Literal["laboratory", "urine_laboratory", "report", "clinical", "vital_signs"]
    source_type: Literal["lab_report", "radiology_report", "patient"]
    source_id: UUID
    source_path: str | None = None
    title: str
    date_source: str
    results: list[TimelineLabValue] = Field(default_factory=list)
    clinical: ClinicalContext | None = None
    vital_signs: VitalSigns | None = None
    inferred_report_type: str | None = None
    report_type_confidence: float | None = None
    report_text: str | None = None
    summary: str | None = None
    file_name: str | None = None
    original_file_available: bool = False


class PatientHealthTimelineDay(BaseModel):
    date: date | None
    entries: list[PatientHealthTimelineEntry]


class PatientHealthTimelineResponse(BaseModel):
    patient_id: UUID
    groups: list[PatientHealthTimelineDay] = Field(default_factory=list)
    total_entries: int = 0
    total_lab_results: int = 0
