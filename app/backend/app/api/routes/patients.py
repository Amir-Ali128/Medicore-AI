"""Persistent patient records and clinical context endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import SessionDep
from app.infrastructure.database.models.patient import Patient
from app.schemas.patient_record import PatientRecordResponse, PatientRecordUpsert

router = APIRouter(prefix="/patients", tags=["patients"])


def _metadata_from_payload(payload: PatientRecordUpsert) -> dict:
    return {
        "full_name": payload.full_name.strip(),
        "age": payload.age,
        "height_cm": payload.height_cm,
        "weight_kg": payload.weight_kg,
        "clinical_context": payload.clinical_context,
        "record_source": "medicore_frontend",
    }


@router.post("", response_model=PatientRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_record(
    payload: PatientRecordUpsert,
    session: SessionDep,
) -> Patient:
    patient = Patient(
        external_ref=f"medicore-{uuid.uuid4()}",
        sex=payload.sex,
        date_of_birth=None,
        is_pregnant=None,
        metadata_json=_metadata_from_payload(payload),
    )
    session.add(patient)
    await session.commit()
    await session.refresh(patient)
    return patient


@router.get("", response_model=list[PatientRecordResponse])
async def list_patient_records(session: SessionDep, limit: int = 100) -> list[Patient]:
    safe_limit = max(1, min(limit, 500))
    stmt = select(Patient).order_by(Patient.updated_at.desc()).limit(safe_limit)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{patient_id}", response_model=PatientRecordResponse)
async def get_patient_record(patient_id: uuid.UUID, session: SessionDep) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    return patient


@router.put("/{patient_id}", response_model=PatientRecordResponse)
async def update_patient_record(
    patient_id: uuid.UUID,
    payload: PatientRecordUpsert,
    session: SessionDep,
) -> Patient:
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")

    patient.sex = payload.sex
    patient.metadata_json = {
        **dict(patient.metadata_json or {}),
        **_metadata_from_payload(payload),
    }
    await session.commit()
    await session.refresh(patient)
    return patient
