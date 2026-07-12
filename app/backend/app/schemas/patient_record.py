"""Schemas for persistent patient and clinical record management."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Sex


class PatientRecordUpsert(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    age: int | None = Field(default=None, ge=0, le=130)
    sex: Sex = Sex.UNKNOWN
    height_cm: float | None = Field(default=None, ge=30, le=260)
    weight_kg: float | None = Field(default=None, ge=1, le=600)
    clinical_context: dict[str, Any] = Field(default_factory=dict)


class PatientRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_ref: str | None
    sex: Sex
    date_of_birth: Any | None
    is_pregnant: bool | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
