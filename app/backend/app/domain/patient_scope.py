"""Validate references against one selected patient before reading or using them.

The existing patient/report models remain the source of truth. These guards do
not infer patient identity from names or clinical content.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from fastapi import HTTPException
from sqlalchemy import select

from app.infrastructure.database.models.analysis_run import AnalysisRun
from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
from app.infrastructure.database.models.doctor_review import DoctorReview
from app.infrastructure.database.models.extraction_job import ExtractionJob
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.infrastructure.database.models.patient import Patient
from app.schemas.radiology_report import DEMO_PATIENT_ID


SOURCE_MODELS = {
    "patient": Patient,
    "lab_report": LabReport,
    "lab_result": LabResult,
    "analysis_run": AnalysisRun,
    "radiology_report": RadiologyReport,
    "report": RadiologyReport,
    "clinical_hypothesis": ClinicalHypothesis,
    "doctor_review": DoctorReview,
    "extraction_job": ExtractionJob,
}


def source_references(metadata):
    """Yield patient and known internal source references from request metadata."""
    if isinstance(metadata, Mapping):
        if metadata.get("patient_id") is not None:
            yield "patient", _source_uuid(metadata["patient_id"])
        for source_type in SOURCE_MODELS:
            source_id = metadata.get(f"{source_type}_id")
            if source_id is not None:
                yield source_type, _source_uuid(source_id)
        entity_type = metadata.get("source_entity_type")
        entity_id = metadata.get("source_entity_id")
        if entity_id is not None and entity_type not in SOURCE_MODELS:
            raise HTTPException(status_code=422, detail="Desteklenmeyen hasta veri kaynağı.")
        if entity_type in SOURCE_MODELS and entity_id is not None:
            yield entity_type, _source_uuid(entity_id)
        for value in metadata.values():
            if isinstance(value, (Mapping, list, tuple)):
                yield from source_references(value)
    elif isinstance(metadata, (list, tuple)):
        for value in metadata:
            yield from source_references(value)


def _source_uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail="Geçersiz hasta/kaynak kimliği.") from exc


async def ensure_source_patient(session, *, patient_id, source_type, source_id, current_user_id=None):
    """Fetch a supported source only when its patient_id matches the selection."""
    model = SOURCE_MODELS.get(source_type)
    if model is None:
        raise HTTPException(status_code=422, detail="Desteklenmeyen hasta veri kaynağı.")
    statement = select(model).where(model.id == _source_uuid(source_id))
    if model is Patient:
        statement = statement.where(model.id == patient_id)
    elif model is DoctorReview:
        statement = statement.join(
            ClinicalHypothesis, model.clinical_hypothesis_id == ClinicalHypothesis.id,
        ).where(ClinicalHypothesis.patient_id == patient_id)
    else:
        statement = statement.where(model.patient_id == patient_id)
    if model in {LabResult, AnalysisRun}:
        statement = statement.join(LabReport, model.lab_report_id == LabReport.id).where(
            LabReport.patient_id == patient_id,
        )
    record = (await session.execute(statement)).scalars().first()
    if record is None:
        raise HTTPException(status_code=404, detail="Seçili hastaya ait kaynak bulunamadı.")
    if patient_id == DEMO_PATIENT_ID:
        if model in {LabReport, RadiologyReport} and (
            current_user_id is None or record.uploaded_by_user_id != current_user_id
        ):
            raise HTTPException(status_code=404, detail="Seçili hastaya ait kaynak bulunamadı.")
        if model in {LabResult, AnalysisRun}:
            await ensure_source_patient(
                session, patient_id=patient_id, source_type="lab_report",
                source_id=record.lab_report_id, current_user_id=current_user_id,
            )
    if model in {ClinicalHypothesis, ExtractionJob} and record.lab_report_id is not None:
        await ensure_source_patient(
            session, patient_id=patient_id, source_type="lab_report",
            source_id=record.lab_report_id, current_user_id=current_user_id,
        )
    if model in {LabResult, ClinicalHypothesis, ExtractionJob} and record.analysis_run_id is not None:
        run = await ensure_source_patient(
            session, patient_id=patient_id, source_type="analysis_run",
            source_id=record.analysis_run_id, current_user_id=current_user_id,
        )
        if record.lab_report_id is not None and run.lab_report_id != record.lab_report_id:
            raise HTTPException(status_code=409, detail="Kaynak ilişkileri uyuşmuyor.")
    if model is DoctorReview:
        await ensure_source_patient(
            session, patient_id=patient_id, source_type="clinical_hypothesis",
            source_id=record.clinical_hypothesis_id, current_user_id=current_user_id,
        )
    return record


async def validate_source_metadata(session, *, patient_id, metadata, current_user_id=None) -> None:
    """Validate explicit internal references, including nested provenance."""
    if isinstance(metadata, Mapping):
        explicit_patient = metadata.get("patient_id")
        if explicit_patient is not None and _source_uuid(explicit_patient) != patient_id:
            raise HTTPException(status_code=409, detail="Kaynak seçili hastaya ait değil.")
        for source_type in SOURCE_MODELS:
            source_id = metadata.get(f"{source_type}_id")
            if source_id is not None:
                await ensure_source_patient(
                    session, patient_id=patient_id, source_type=source_type,
                    source_id=source_id, current_user_id=current_user_id,
                )
        entity_type = metadata.get("source_entity_type")
        entity_id = metadata.get("source_entity_id")
        if entity_id is not None and entity_type not in SOURCE_MODELS:
            raise HTTPException(status_code=422, detail="Desteklenmeyen hasta veri kaynağı.")
        if entity_type in SOURCE_MODELS and entity_id is not None:
            await ensure_source_patient(
                session, patient_id=patient_id, source_type=entity_type,
                source_id=entity_id, current_user_id=current_user_id,
            )
        for value in metadata.values():
            if isinstance(value, (Mapping, list, tuple)):
                await validate_source_metadata(session, patient_id=patient_id, metadata=value, current_user_id=current_user_id)
    elif isinstance(metadata, (list, tuple)):
        for value in metadata:
            await validate_source_metadata(session, patient_id=patient_id, metadata=value, current_user_id=current_user_id)
