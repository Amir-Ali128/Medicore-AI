"""Schemas for persistent patient and clinical record management."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import Sex


_PATIENT_PROTOCOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{1,31}$")


class PatientRecordUpsert(BaseModel):
    protocol_no: str = Field(min_length=2, max_length=32)
    age: int | None = Field(default=None, ge=0, le=130)
    sex: Sex = Sex.UNKNOWN
    height_cm: float | None = Field(default=None, ge=30, le=260)
    weight_kg: float | None = Field(default=None, ge=1, le=600)
    clinical_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("protocol_no")
    @classmethod
    def normalize_patient_protocol_no(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _PATIENT_PROTOCOL_PATTERN.fullmatch(normalized):
            raise ValueError(
                "Protokol numarası 2-32 karakter olmalı; yalnızca harf, rakam, "+
                "nokta, tire, alt çizgi ve / içerebilir."
            )
        return normalized


class PatientRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    protocol_no: str
    external_ref: str | None
    sex: Sex
    date_of_birth: Any | None
    is_pregnant: bool | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
