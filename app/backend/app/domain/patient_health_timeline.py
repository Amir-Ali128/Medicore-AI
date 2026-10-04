"""Patient-scoped read projection over existing records; never persists copies."""
from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from app.domain.patient_clinical_context import normalize_patient_clinical, patient_clinical_context
from app.domain.document_dates import date_values, extract_document_dates, resolve_timeline_date
from app.domain.lab_result_classification import classify_lab_result
from app.domain.report_type_inference import infer_existing_report_type
from app.domain.patient_scope import validate_source_metadata
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.schemas.patient_health_timeline import (
    PatientHealthTimelineDay, PatientHealthTimelineEntry,
    PatientHealthTimelineResponse, TimelineLabValue,
)

def _mapping(value: Any) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _common_date(values: list[TimelineLabValue], key: str) -> date | None:
    days = {getattr(value, key) for value in values}
    return days.pop() if len(days) == 1 else None


def _lab_value(*, identifier: str, label: str, value: Any, unit: str | None,
               metadata: dict, record: dict) -> tuple[TimelineLabValue, Any]:
    resolved = resolve_timeline_date(record, kind="lab")
    reference = _mapping(metadata.get("reference_details"))
    classification = classify_lab_result(
        value=value, unit=unit,
        reference_text=metadata.get("reference_text") or metadata.get("raw_reference"),
        reference_low=reference.get("minimum", metadata.get("reference_min")),
        reference_high=reference.get("maximum", metadata.get("reference_max")),
        reference_unit=reference.get("unit") or metadata.get("reference_unit"),
        ingestion_reasons=metadata.get("ingestion_reasons") or (),
    )
    return TimelineLabValue(
        id=identifier, test_name=label, value=value, unit=unit,
        reference_text=metadata.get("reference_text"), status=classification.status,
        reference_low=classification.reference_low, reference_high=classification.reference_high,
        raw_reference=classification.raw_reference,
        **{key: resolved.dates[key] for key in ("specimen_date", "result_date", "document_date", "uploaded_at")},
        event_date=resolved.date,
    ), resolved


def _same_patient(value: Any, patient_id: Any) -> bool:
    return str(value) == str(patient_id)


def _context_matches_patient(value: Any, patient_id: Any) -> bool:
    # A legacy source with an explicit different patient id must not supply
    # clinical/vital context to another patient's projection.
    if isinstance(value, Mapping):
        if value.get("patient_id") is not None and not _same_patient(value["patient_id"], patient_id):
            return False
        return all(_context_matches_patient(item, patient_id) for item in value.values())
    if isinstance(value, list):
        return all(_context_matches_patient(item, patient_id) for item in value)
    return True


def _urine(metadata: dict, label: str = "") -> bool:
    specimen = str(metadata.get("specimen_type") or metadata.get("specimen") or "").casefold()
    text = label.casefold()
    return specimen in {"urine", "idrar", "urinalysis"} or any(marker in text for marker in ("idrar", "urine", "urinalysis"))


def build_patient_health_timeline(patient, lab_reports, lab_results, reports) -> PatientHealthTimelineResponse:
    patient_id = patient.id
    by_day = defaultdict(list)
    source_labs = {str(item.id): item for item in lab_reports if _same_patient(item.patient_id, patient_id)}
    rows_by_report = defaultdict(list)
    for row in lab_results:
        if _same_patient(row.patient_id, patient_id) and str(row.lab_report_id) in source_labs:
            rows_by_report[str(row.lab_report_id)].append(row)

    def add_context(source, raw, metadata, source_type, source_path, *, current=False):
        if not _context_matches_patient(raw, patient_id):
            return
        clinical = patient_clinical_context(metadata) if current else normalize_patient_clinical(raw, metadata)
        raw = _mapping(raw)
        exam = _mapping(raw.get("physical_exam"))
        record = {
            **date_values(metadata), **date_values(raw),
            "examination_date": (None if "event_date" in raw else raw.get("examination_date") or exam.get("examination_date")),
            "report_date": getattr(source, "report_date", None),
            "created_at": getattr(source, "created_at", None),
        }
        if "event_date" in raw:
            record["event_date"] = raw["event_date"]
        clinical_date = resolve_timeline_date(record, kind="clinical")
        clinical_day, clinical_date_source = clinical_date.date, clinical_date.source
        if any((clinical.complaints, clinical.history, clinical.medications, clinical.notes)):
            by_day[clinical_day].append(PatientHealthTimelineEntry(
                id=f"{source_type}:{source.id}:clinical", patient_id=patient_id,
                kind="clinical", source_type=source_type, source_id=source.id, source_path=source_path,
                title="Klinik Bilgi", date_source=clinical_date_source,
                event_date=clinical_day, uploaded_at=clinical_date.dates["uploaded_at"],
                clinical=clinical.model_copy(update={"vital_signs": None}),
            ))
        if clinical.vital_signs and any(value is not None for value in clinical.vital_signs.model_dump().values()):
            vitals = _mapping(raw.get("vital_signs"))
            vital_date = resolve_timeline_date({
                **record, "event_date": raw.get("vitals_event_date") or raw.get("event_date"),
                "measurement_date": (None if "vitals_event_date" in raw else vitals.get("measurement_date") or vitals.get("measured_at") or exam.get("measurement_date")),
            }, kind="vital_signs")
            vital_day, vital_date_source = vital_date.date, vital_date.source
            by_day[vital_day].append(PatientHealthTimelineEntry(
                id=f"{source_type}:{source.id}:vitals", patient_id=patient_id,
                kind="vital_signs", source_type=source_type, source_id=source.id, source_path=source_path,
                title="Vital Bulgular", date_source=vital_date_source, vital_signs=clinical.vital_signs,
                event_date=vital_day, uploaded_at=vital_date.dates["uploaded_at"],
            ))

    for report in source_labs.values():
        metadata = _mapping(getattr(report, "metadata_json", None))
        grouped_rows = defaultdict(list)
        rows = rows_by_report[str(report.id)]
        # Canonical rows are the source of truth; legacy metadata is read only
        # when no structured result records were ever stored for this report.
        if rows:
            for row in rows:
                row_metadata = _mapping(getattr(row, "metadata_json", None))
                label = getattr(row, "raw_parameter_name", None) or getattr(row, "canonical_name", None) or "Laboratuvar sonucu"
                kind = "urine_laboratory" if _urine(row_metadata, label) or _urine(metadata) else "laboratory"
                value = getattr(row, "raw_value", None)
                if value is None:
                    value = getattr(row, "normalized_value", None)
                if isinstance(value, Decimal):
                    value = str(value)
                row_metadata.setdefault("reference_min", getattr(row, "reference_min", None))
                row_metadata.setdefault("reference_max", getattr(row, "reference_max", None))
                lab_value, resolved = _lab_value(
                    identifier=str(row.id), label=label, value=value, unit=getattr(row, "unit", None),
                    metadata=row_metadata, record={
                        **date_values(metadata), **date_values(row_metadata),
                        "measured_at": getattr(row, "measured_at", None),
                        "report_date": getattr(report, "report_date", None),
                        "created_at": getattr(report, "created_at", None),
                    },
                )
                grouped_rows[(resolved.date, kind, resolved.source)].append(lab_value)
        else:
            legacy_rows = metadata.get("simple_case_results")
            for index, item in enumerate(legacy_rows if isinstance(legacy_rows, list) else []):
                if not isinstance(item, Mapping) or not _context_matches_patient(item, patient_id):
                    continue
                label = str(item.get("test_name") or "Laboratuvar sonucu")
                kind = "urine_laboratory" if _urine(metadata, label) else "laboratory"
                lab_value, resolved = _lab_value(
                    identifier=f"{report.id}:metadata:{index}", label=label, value=item.get("value"),
                    unit=item.get("unit"), metadata={**_mapping(item.get("source_metadata")), **dict(item)},
                    record={**date_values(metadata), **date_values(item),
                            "report_date": getattr(report, "report_date", None),
                            "created_at": getattr(report, "created_at", None)},
                )
                grouped_rows[(resolved.date, kind, resolved.source)].append(lab_value)
        for (row_day, kind, date_source), values in grouped_rows.items():
            by_day[row_day].append(PatientHealthTimelineEntry(
                id=f"lab_report:{report.id}:{row_day}:{kind}:{date_source}", patient_id=patient_id,
                kind=kind, source_type="lab_report", source_id=report.id,
                source_path="results" if rows else "metadata_json.simple_case_results",
                title="İdrar / Laboratuvar" if kind == "urine_laboratory" else "Laboratuvar",
                date_source=date_source, results=values, file_name=getattr(report, "file_name", None),
                event_date=row_day,
                **{key: _common_date(values, key) for key in ("specimen_date", "result_date", "document_date", "uploaded_at")},
                original_file_available=metadata.get("original_file_stored") is True,
            ))
            # A result-release notice references the original rows. No values or
            # DB records are duplicated, and clinical sample chronology stays put.
            released = defaultdict(list)
            for value in values:
                if row_day and value.result_date and value.result_date > row_day:
                    released[value.result_date].append(value)
            for release_day, released_values in released.items():
                by_day[release_day].append(PatientHealthTimelineEntry(
                    id=f"lab_report:{report.id}:{row_day}:{kind}:{date_source}:released:{release_day}",
                    patient_id=patient_id, kind="lab_result_available", source_type="lab_report",
                    source_id=report.id, source_path="results" if rows else "metadata_json.simple_case_results",
                    title="Geç Sonuçlanan Laboratuvar", date_source="result_date",
                    event_date=row_day, specimen_date=_common_date(released_values, "specimen_date"),
                    result_date=release_day, document_date=_common_date(released_values, "document_date"),
                    uploaded_at=_common_date(released_values, "uploaded_at"),
                    result_ids=[value.id for value in released_values],
                    file_name=getattr(report, "file_name", None),
                    original_file_available=metadata.get("original_file_stored") is True,
                ))
        if isinstance(metadata.get("clinical_context"), Mapping):
            add_context(report, metadata["clinical_context"], metadata, "lab_report", "metadata_json.clinical_context")

    for report in reports:
        if not _same_patient(report.patient_id, patient_id):
            continue
        metadata = _mapping(getattr(report, "metadata_json", None))
        inference = infer_existing_report_type(report)
        resolved = resolve_timeline_date({
            **extract_document_dates(getattr(report, "original_text", None)),
            **date_values(metadata), "report_date": getattr(report, "report_date", None),
            "created_at": getattr(report, "created_at", None),
        }, kind=inference.report_type if inference.report_type in {"ULTRASOUND", "CT", "MRI", "XRAY", "X_RAY", "ECG", "ECHO", "ECHOCARDIOGRAPHY"} else "report")
        report_day, date_source = resolved.date, resolved.source
        by_day[report_day].append(PatientHealthTimelineEntry(
            id=f"radiology_report:{report.id}", patient_id=patient_id,
            kind="report", source_type="radiology_report", source_id=report.id,
            title="Rapor", date_source=date_source, inferred_report_type=inference.report_type,
            event_date=report_day,
            **{key: resolved.dates[key] for key in ("specimen_date", "result_date", "document_date", "uploaded_at", "exam_date", "consultation_date")},
            report_type_confidence=inference.confidence,
            report_text=getattr(report, "original_text", None), summary=getattr(report, "summary", None),
            file_name=getattr(report, "file_name", None), original_file_available=metadata.get("original_file_stored") is True,
        ))
        if isinstance(metadata.get("clinical_context"), Mapping):
            add_context(report, metadata["clinical_context"], metadata, "radiology_report", "metadata_json.clinical_context")

    metadata = {**_mapping(getattr(patient, "metadata_json", None)), "sex": str(patient.sex)}
    snapshot = _mapping(metadata.get("simple_case"))
    raw = snapshot.get("clinical") if isinstance(snapshot.get("clinical"), Mapping) else metadata.get("clinical_context")
    add_context(patient, raw, metadata, "patient", "metadata_json.simple_case.clinical" if isinstance(snapshot.get("clinical"), Mapping) else "metadata_json.clinical_context", current=True)
    order = sorted(by_day, key=lambda day: (day is not None, day or date.min), reverse=True)
    groups = [PatientHealthTimelineDay(date=day, entries=by_day[day]) for day in order]
    return PatientHealthTimelineResponse(
        patient_id=patient_id, groups=groups,
        total_entries=sum(len(group.entries) for group in groups),
        total_lab_results=sum(len(entry.results) for group in groups for entry in group.entries),
    )


async def load_patient_health_timeline(patient, session) -> PatientHealthTimelineResponse:
    await validate_source_metadata(session, patient_id=patient.id, metadata=patient.metadata_json)
    lab_reports = (await session.execute(select(LabReport).where(LabReport.patient_id == patient.id))).scalars().all()
    # Check both sides of the FK: malformed legacy result associations cannot
    # leak a row even if its lab_report_id points to this patient's report.
    lab_results = (await session.execute(
        select(LabResult).join(LabReport, LabResult.lab_report_id == LabReport.id)
        .where(LabResult.patient_id == patient.id, LabReport.patient_id == patient.id)
    )).scalars().all()
    reports = (await session.execute(select(RadiologyReport).where(RadiologyReport.patient_id == patient.id))).scalars().all()
    async def safe_sources(records):
        safe = []
        for record in records:
            try:
                await validate_source_metadata(
                    session, patient_id=patient.id, metadata=record.metadata_json,
                )
            except HTTPException as exc:
                if exc.status_code in {404, 409, 422}:
                    continue
                raise
            safe.append(record)
        return safe

    lab_reports = await safe_sources(lab_reports)
    lab_results = await safe_sources(lab_results)
    reports = await safe_sources(reports)
    return build_patient_health_timeline(patient, lab_reports, lab_results, reports)
