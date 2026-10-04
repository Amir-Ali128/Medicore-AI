"""Semantic document dates, separate from the time a file reached the server."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

CLINIC_TIMEZONE = ZoneInfo("Europe/Istanbul")
SEMANTIC_DATE_FIELDS = (
    "event_date", "specimen_date", "result_date", "document_date", "uploaded_at",
    "exam_date", "consultation_date",
)


def calendar_day(value: Any) -> date | None:
    """Date-only values stay put; timestamps use the clinic's calendar day."""
    if isinstance(value, datetime):
        return value.astimezone(CLINIC_TIMEZONE).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            return date.fromisoformat(text)
        except ValueError:
            try:
                return calendar_day(datetime.fromisoformat(text.replace("Z", "+00:00")))
            except ValueError:
                for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        return datetime.strptime(text, fmt).date()
                    except ValueError:
                        continue
    return None


def date_values(record: Mapping | None) -> dict[str, Any]:
    """Read additive fields and legacy JSON without overwriting explicit values."""
    record = record if isinstance(record, Mapping) else {}
    result: dict[str, Any] = {}
    for source in (
        record,
        record.get("source_metadata"),
        record.get("metadata"),
        record.get("metadata_json"),
    ):
        if isinstance(source, Mapping):
            for key, value in source.items():
                if key not in result or calendar_day(result[key]) is None:
                    if calendar_day(value) is not None:
                        result[key] = value
    return result


@dataclass(frozen=True)
class ResolvedTimelineDate:
    date: date | None
    source: str
    dates: dict[str, date | None]


def resolve_timeline_date(record: Mapping, *, kind: str) -> ResolvedTimelineDate:
    values = date_values(record)
    if kind in {"laboratory", "urine_laboratory", "lab"}:
        order = (
            "specimen_date", "event_date", "measured_at", "test_date",
            "document_date", "report_date", "result_date", "uploaded_at", "created_at",
        )
    elif kind in {"ULTRASOUND", "CT", "MRI", "XRAY", "X_RAY", "ECG", "ECHO", "ECHOCARDIOGRAPHY", "imaging"}:
        order = (
            "exam_date", "event_date", "examination_date", "document_date", "report_date",
            "specimen_date", "result_date", "uploaded_at", "created_at",
        )
    elif kind in {"CONSULTATION", "consultation", "report"}:
        order = (
            "consultation_date", "document_date", "event_date", "report_date",
            "exam_date", "examination_date", "specimen_date", "result_date", "uploaded_at", "created_at",
        )
    elif kind == "clinical":
        order = (
            "event_date", "examination_date", "clinical_context_recorded_at",
            "clinical_recorded_at", "document_date", "report_date", "result_date",
            "uploaded_at", "created_at",
        )
    elif kind == "vital_signs":
        order = (
            "event_date", "measurement_date", "measured_at", "vitals_recorded_at",
            "examination_date", "clinical_context_recorded_at", "clinical_recorded_at",
            "document_date", "report_date", "result_date", "uploaded_at", "created_at",
        )
    else:
        order = (
            "event_date", "specimen_date", "document_date", "report_date",
            "result_date", "uploaded_at", "created_at",
        )
    dates = {key: calendar_day(values.get(key)) for key in SEMANTIC_DATE_FIELDS}
    dates["uploaded_at"] = dates["uploaded_at"] or calendar_day(values.get("created_at"))
    for key in order:
        parsed = calendar_day(values.get(key))
        if parsed is not None:
            return ResolvedTimelineDate(parsed, key, dates)
    return ResolvedTimelineDate(None, "unknown", dates)


_TRANSLATION = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")
_DATE_TOKEN = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})"
_DATE_LABELS = {
    "specimen_date": r"(?:numune\s*(?:alma|alim|alinma|kabul)?|ornek\s*(?:alma|alim|alinma)?|specimen\s*(?:collection)?|sample\s*(?:collection)?)\s*(?:tarihi|date)",
    "result_date": r"(?:sonuc\s*(?:onay|cikis|verilme|raporlama)?|result\s*(?:release|reported)?|reporting)\s*(?:tarihi|date)",
    "document_date": r"(?:rapor|belge|document|report)\s*(?:tarihi|date)",
    "exam_date": r"(?:tetkik|inceleme|cekim|muayene|exam|examination)\s*(?:tarihi|date)",
    "consultation_date": r"(?:konsultasyon|consultation)\s*(?:tarihi|date)",
    "event_date": r"(?:olay|event)\s*(?:tarihi|date)",
}


def extract_document_dates(text: str | None) -> dict[str, date]:
    """Read explicitly labelled dates; conflicting dates are left to row readers.

    An unlabelled date, a patient's birth date or a file name supplies no
    specimen/result/examination date. Never infer a missing date from upload.
    """
    folded = (text or "").translate(_TRANSLATION).casefold()
    output: dict[str, date] = {}
    for key, label in _DATE_LABELS.items():
        found = {
            parsed
            for match in re.finditer(rf"\b{label}\s*[:：-]?\s*({_DATE_TOKEN})", folded)
            if (parsed := calendar_day(match.group(1))) is not None
        }
        if len(found) == 1:
            output[key] = found.pop()
    return output
