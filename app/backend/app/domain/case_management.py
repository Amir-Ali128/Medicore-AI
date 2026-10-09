"""Display names are metadata, never patient/source identifiers."""
from __future__ import annotations

import unicodedata
import uuid

from fastapi import HTTPException
from sqlalchemy import select, text

from app.infrastructure.database.models.patient import Patient
from app.schemas.radiology_report import DEMO_PATIENT_ID

DUPLICATE_CASE_NAME = "Bu isimde başka bir vaka zaten mevcut."


def case_display_name(protocol_no: str, metadata: dict | None) -> str:
    name = (metadata or {}).get("case_name")
    return name.strip() if isinstance(name, str) and name.strip() else protocol_no


def normalized_case_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name.strip()).casefold()


async def lock_case_names(session) -> None:
    # Serialize the availability check and write across API workers. This is a
    # transaction lock, released by commit/rollback; no schema change is needed.
    get_bind = getattr(session, "get_bind", None)
    if callable(get_bind) and get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(742190051)"))


async def ensure_case_name_available(session, name: str, *, exclude_id: uuid.UUID | None = None) -> None:
    # Read labels only; availability checks do not load other clinical records.
    stmt = select(Patient.id, Patient.protocol_no, Patient.metadata_json["case_name"].as_string()).where(Patient.id != DEMO_PATIENT_ID)
    if exclude_id is not None:
        stmt = stmt.where(Patient.id != exclude_id)
    expected = normalized_case_name(name)
    for _id, protocol, stored_name in (await session.execute(stmt)).all():
        if normalized_case_name(case_display_name(protocol, {"case_name": stored_name})) == expected:
            raise HTTPException(status_code=409, detail=DUPLICATE_CASE_NAME)
