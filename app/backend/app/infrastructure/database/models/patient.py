"""Patient model.

Deliberately minimal: this module structures lab data and drives demographic
range selection (sex, age, pregnancy), so only the attributes required for that
are stored. Direct identifiers are kept out; `external_ref` holds an opaque
reference owned by the calling system.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Boolean, Date, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import Sex
from app.domain.patient_protocol import generate_protocol_no
from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    sex_enum,
)


class Patient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "patients"

    # Human-readable, non-PII patient reference. This is intentionally
    # non-sequential and must never be treated as an authentication secret.
    protocol_no: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False,
        default=generate_protocol_no,
    )

    # Opaque reference to the patient in the source/calling system (no PII).
    external_ref: Mapped[str | None] = mapped_column(
        String(128), unique=True, index=True
    )

    sex: Mapped[Sex] = mapped_column(
        sex_enum,
        default=Sex.UNKNOWN,
        nullable=False,
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date)

    # Tri-state: True / False / NULL (unknown or not applicable).
    is_pregnant: Mapped[bool | None] = mapped_column(Boolean)

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<Patient id={self.id!s} protocol_no={self.protocol_no!r} "
            f"sex={self.sex.value}>"
        )
