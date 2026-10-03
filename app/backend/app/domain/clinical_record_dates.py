"""Stable fallback dates for clinical records already stored in JSON metadata."""

from datetime import UTC, datetime

from app.schemas.simple_case import ClinicalContext


def stamp_clinical_record_dates(
    metadata: dict,
    previous: ClinicalContext,
    current: ClinicalContext,
    *,
    at: datetime | None = None,
) -> dict:
    updated = dict(metadata)
    recorded_at = (at or datetime.now(UTC)).isoformat()
    fields = ("complaints", "history", "medications", "notes")
    if any(getattr(previous, name) != getattr(current, name) for name in fields):
        updated["clinical_recorded_at"] = recorded_at
    if previous.vital_signs != current.vital_signs:
        updated["vitals_recorded_at"] = recorded_at
    return updated
