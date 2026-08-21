"""Persistent patient records and clinical context endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.domain.enums import UserRole
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.schemas.patient_record import PatientRecordResponse, PatientRecordUpsert

router = APIRouter(prefix="/patients", tags=["patients"])


def _metadata_from_payload(
    payload: PatientRecordUpsert,
    *,
    owner_user_id: uuid.UUID,
) -> dict:
    return {
        "age": payload.age,
        "height_cm": payload.height_cm,
        "weight_kg": payload.weight_kg,
        "clinical_context": payload.clinical_context,
        "record_source": "medicore_frontend",
        "owner_user_id": str(owner_user_id),
    }


def _ensure_patient_access(patient: Patient, current_user: User) -> None:
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

    patient = Patient(
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


@router.get("", response_model=list[PatientRecordResponse])
async def list_patient_records(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = 100,
) -> list[Patient]:
    safe_limit = max(1, min(limit, 500))
    stmt = select(Patient).order_by(Patient.updated_at.desc())

    if current_user.role == UserRole.PATIENT:
        stmt = stmt.where(
            Patient.metadata_json.contains(
                {"owner_user_id": str(current_user.id)},
            )
        )

    stmt = stmt.limit(safe_limit)
    return list((await session.execute(stmt)).scalars().all())


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

    await _ensure_protocol_available(
        session,
        payload.protocol_no,
        exclude_patient_id=patient_id,
    )

    patient.protocol_no = payload.protocol_no
    patient.sex = payload.sex
    patient.metadata_json = {
        **dict(patient.metadata_json or {}),
        **_metadata_from_payload(
            payload,
            owner_user_id=current_user.id,
        ),
    }
    patient.metadata_json.pop("full_name", None)

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
