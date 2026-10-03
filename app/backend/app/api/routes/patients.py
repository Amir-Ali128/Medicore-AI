"""Persistent patient records and clinical context endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.domain.enums import UserRole
from app.domain.clinical_record_dates import stamp_clinical_record_dates
from app.domain.patient_clinical_context import normalize_patient_clinical, patient_clinical_context
from app.domain.patient_scope import validate_source_metadata
from app.domain.simple_case import case_fingerprint
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.schemas.patient_record import PatientRecordResponse, PatientRecordUpsert
from app.schemas.simple_case import VitalSigns
from app.schemas.radiology_report import DEMO_PATIENT_ID

router = APIRouter(prefix="/patients", tags=["patients"])


def _metadata_from_payload(
    payload: PatientRecordUpsert,
    *,
    owner_user_id: uuid.UUID,
) -> dict:
    metadata = {
        "age": payload.age,
        "height_cm": payload.height_cm,
        "weight_kg": payload.weight_kg,
        "clinical_context": payload.clinical_context,
        "record_source": "medicore_frontend",
        "owner_user_id": str(owner_user_id),
    }
    if 'vital_signs' in payload.clinical_context:
        metadata.pop('height_cm')
        metadata.pop('weight_kg')
    return metadata


def _ensure_patient_access(patient: Patient, current_user: User) -> None:
    if patient.id == DEMO_PATIENT_ID:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    if current_user.role != UserRole.PATIENT:
        return

    owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
    if owner_user_id != str(current_user.id):
        # Do not reveal whether another account's patient record exists.
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")


async def _ensure_protocol_available(
    session: SessionDep,
    protocol_no: str,
    *,
    exclude_patient_id: uuid.UUID | None = None,
) -> None:
    stmt = select(Patient.id).where(Patient.protocol_no == protocol_no)
    if exclude_patient_id is not None:
        stmt = stmt.where(Patient.id != exclude_patient_id)

    existing_id = (await session.execute(stmt)).scalar_one_or_none()
    if existing_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu protokol numarası başka bir hasta kaydında kullanılıyor.",
        )


@router.post("", response_model=PatientRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_record(
    payload: PatientRecordUpsert,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Patient:
    await _ensure_protocol_available(session, payload.protocol_no)
    patient_id = uuid.uuid4()
    await validate_source_metadata(session, patient_id=patient_id, metadata=payload.clinical_context)
    patient = Patient(
        id=patient_id,
        protocol_no=payload.protocol_no,
        external_ref=f"medicore-{uuid.uuid4()}",
        sex=payload.sex,
        date_of_birth=None,
        is_pregnant=None,
        metadata_json=_metadata_from_payload(
            payload,
            owner_user_id=current_user.id,
        ),
    )
    session.add(patient)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu protokol numarası başka bir hasta kaydında kullanılıyor.",
        ) from exc

    await session.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient_record(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    """Permanently delete a patient record and any lab/radiology data tied to it."""
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    _ensure_patient_access(patient, current_user)

    await session.delete(patient)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu hastaya bağlı kayıtlar olduğu için silinemedi.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[PatientRecordResponse])
async def list_patient_records(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = 100,
) -> list[Patient]:
    safe_limit = max(1, min(limit, 500))
    stmt = select(Patient).where(Patient.id != DEMO_PATIENT_ID).order_by(Patient.updated_at.desc())

    if current_user.role == UserRole.PATIENT:
        stmt = stmt.where(
            Patient.metadata_json.contains(
                {"owner_user_id": str(current_user.id)},
            )
        )

    stmt = stmt.limit(safe_limit)
    records = list((await session.execute(stmt)).scalars().all())
    safe_records = []
    for patient in records:
        try:
            await validate_source_metadata(session, patient_id=patient.id, metadata=patient.metadata_json)
        except HTTPException as exc:
            if exc.status_code in {404, 409, 422}:
                continue
            raise
        safe_records.append(patient)
    return safe_records


@router.get("/{patient_id}", response_model=PatientRecordResponse)
async def get_patient_record(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    _ensure_patient_access(patient, current_user)
    await validate_source_metadata(session, patient_id=patient_id, metadata=patient.metadata_json)
    return patient


@router.put("/{patient_id}", response_model=PatientRecordResponse)
async def update_patient_record(
    patient_id: uuid.UUID,
    payload: PatientRecordUpsert,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    _ensure_patient_access(patient, current_user)

    await validate_source_metadata(session, patient_id=patient_id, metadata=payload.clinical_context)

    await _ensure_protocol_available(
        session,
        payload.protocol_no,
        exclude_patient_id=patient_id,
    )

    patient.protocol_no = payload.protocol_no
    if "sex" in payload.model_fields_set:
        patient.sex = payload.sex
    metadata = dict(patient.metadata_json or {})
    previous = patient_clinical_context({**metadata, "sex": str(patient.sex)})
    updated_metadata = _metadata_from_payload(payload, owner_user_id=current_user.id)
    # Editing demographics must never transfer ownership to the editor.
    updated_metadata.pop("owner_user_id")
    for field in ("age", "height_cm", "weight_kg", "clinical_context"):
        if field not in payload.model_fields_set:
            updated_metadata.pop(field, None)
    metadata.update(updated_metadata)
    metadata.pop("full_name", None)

    clinical_fields = {"clinical_context", "age", "sex", "height_cm", "weight_kg"}
    if clinical_fields & payload.model_fields_set:
        context_updated = "clinical_context" in payload.model_fields_set
        clinical = (
            normalize_patient_clinical(payload.clinical_context, {**metadata, "sex": str(patient.sex)})
            if context_updated else previous
        )
        if context_updated and "vital_signs" not in payload.clinical_context:
            # Older clients may edit history without knowing the new vital fields.
            # Only explicitly supplied legacy measurements replace stored values.
            raw = payload.clinical_context
            legacy_fields = {
                "patient_information": {"height_cm": "height_cm", "weight_kg": "weight_kg"},
                "physical_exam": {
                    "blood_pressure_systolic": "systolic_bp",
                    "blood_pressure_diastolic": "diastolic_bp",
                    "pulse_bpm": "heart_rate", "respiratory_rate": "respiratory_rate",
                    "temperature_c": "temperature", "oxygen_saturation_percent": "spo2",
                },
            }
            updates = {}
            for section, fields in legacy_fields.items():
                values = raw.get(section)
                if isinstance(values, dict):
                    for old, new in fields.items():
                        if old in values:
                            updates[new] = getattr(clinical.vital_signs or VitalSigns(), new)
            vitals = previous.vital_signs or VitalSigns()
            clinical = clinical.model_copy(update={"vital_signs": vitals.model_copy(update=updates)})
        if not context_updated or "vital_signs" not in payload.clinical_context:
            updates = {
                field: getattr(payload, field) for field in ("height_cm", "weight_kg")
                if field in payload.model_fields_set
            }
            if updates:
                clinical = clinical.model_copy(update={
                    "vital_signs": (clinical.vital_signs or VitalSigns()).model_copy(update=updates),
                })
        clinical = clinical.model_copy(update={
            field: getattr(payload, field) for field in ("age", "sex")
            if field in payload.model_fields_set
        })
        # Keep the legacy context readable, with one structured measurement source.
        stored_context = metadata.get("clinical_context")
        raw_context = dict(stored_context) if isinstance(stored_context, dict) else {}
        raw_context.update(age=clinical.age, sex=str(clinical.sex),
                           vital_signs=clinical.vital_signs.model_dump(mode="json") if clinical.vital_signs else None)
        metadata["clinical_context"] = raw_context
        metadata = stamp_clinical_record_dates(metadata, previous, clinical)
        metadata["age"] = clinical.age
        metadata.pop("height_cm", None)
        metadata.pop("weight_kg", None)
        snapshot = metadata.get("simple_case")
        if isinstance(snapshot, dict):
            snapshot = {**snapshot, "clinical": clinical.model_dump(mode="json")}
            metadata["simple_case"] = snapshot
            report = metadata.get("simple_case_ai_report")
            if isinstance(report, dict) and report.get("case_fingerprint") != case_fingerprint(snapshot):
                metadata.pop("simple_case_ai_report", None)
    patient.metadata_json = metadata

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu protokol numarası başka bir hasta kaydında kullanılıyor.",
        ) from exc

    await session.refresh(patient)
    return patient
