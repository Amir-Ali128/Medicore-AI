"""Pydantic v2 schemas for lab report extraction.

Extraction only: these models carry lab test names, values, units, reference
ranges, and dates that Claude reads off an uploaded file. No diagnosis, no
interpretation, no treatment advice.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lab_analysis import AnalysisPipelineResult


class ExtractedLabValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_parameter_name: str | None = None
    raw_value: str | None = None
    normalized_value: Decimal | None = None
    unit: str | None = None
    extracted_reference_min: Decimal | None = None
    extracted_reference_max: Decimal | None = None
    extracted_unit: str | None = None
    measured_at: date | None = None
    needs_review: bool = False
    extraction_note: str | None = None


class LabExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    values: list[ExtractedLabValue] = Field(default_factory=list)
    overall_needs_review: bool = False
    extraction_confidence: float | None = None
    source_file_name: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ExtractionAndAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    extraction: LabExtractionResult
    analysis: AnalysisPipelineResult
