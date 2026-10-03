"""Patient timeline routes.

Operational audit-trail endpoints. No diagnosis, no treatment advice, no Claude,
no clinical interpretation.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    PatientTimelineRepositoryDep,
    PatientTimelineServiceDep,
    SessionDep,
)
from app.schemas.patient_timeline import (
    PatientTimelineEventCreate,
    PatientTimelineEventResponse,
    PatientTimelineListResponse,
)
from app.api.routes.auth import get_current_active_user
from app.api.routes.patients import _ensure_patient_access
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.domain.patient_health_timeline import load_patient_health_timeline
from app.schemas.patient_health_timeline import PatientHealthTimelineResponse
from app.domain.patient_scope import validate_source_metadata
from app.schemas.radiology_report import DEMO_PATIENT_ID

router = APIRouter(prefix="/timeline", tags=["patient-timeline"])

_EVENT_NOT_FOUND = "Timeline event not found."


async def _validate_event_sources(event, session: SessionDep) -> None:
    references = {
        name: getattr(event, name, None)
        for name in (
            "patient_id", "lab_report_id", "analysis_run_id", "clinical_hypothesis_id",
            "doctor_review_id", "extraction_job_id", "source_entity_type", "source_entity_id",
            "metadata_json",
        )
    }
    await validate_source_metadata(session, patient_id=event.patient_id, metadata=references)


async def _safe_patient_events(events, patient_id, session: SessionDep) -> list:
    safe = []
    for event in events:
        if event.patient_id != patient_id:
            continue
        try:
            await _validate_event_sources(event, session)
        except HTTPException as exc:
            if exc.status_code in {404, 409, 422}:
                continue
            raise
        safe.append(event)
    return safe


async def _check_patient_access(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: User,
) -> None:
    if patient_id == DEMO_PATIENT_ID:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    patient = await session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    _ensure_patient_access(patient, current_user)


@router.post(
    "/events",
    response_model=PatientTimelineEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_timeline_event(
    payload: PatientTimelineEventCreate,
    session: SessionDep,
    service: PatientTimelineServiceDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PatientTimelineEventResponse:
    await _check_patient_access(payload.patient_id, session, current_user)
    await _validate_event_sources(payload, session)
    payload = payload.model_copy(update={"actor_user_id": current_user.id})
    try:
        event = await service.create_event(payload)
        await session.commit()
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from None
    except Exception:
        await session.rollback()
        raise
    return PatientTimelineEventResponse.model_validate(event)


@router.get(
    "/patients/{patient_id}/health-history",
    response_model=PatientHealthTimelineResponse,
)
async def get_patient_health_history(
    patient_id: uuid.UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PatientHealthTimelineResponse:
    # _check_patient_access excludes the shared upload holding identity.
    await _check_patient_access(patient_id, session, current_user)
    patient = await session.get(Patient, patient_id)
    return await load_patient_health_timeline(patient, session)


@router.get(
    "/events/{timeline_event_id}",
    response_model=PatientTimelineEventResponse,
)
async def get_timeline_event(
    timeline_event_id: uuid.UUID,
    repository: PatientTimelineRepositoryDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PatientTimelineEventResponse:
    event = await repository.get_by_id(timeline_event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_EVENT_NOT_FOUND
        )
    await _check_patient_access(event.patient_id, session, current_user)
    await _validate_event_sources(event, session)
    return event


@router.get(
    "/patients/{patient_id}",
    response_model=PatientTimelineListResponse,
)
async def list_patient_timeline(
    patient_id: uuid.UUID,
    service: PatientTimelineServiceDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int | None = None,
) -> PatientTimelineListResponse:
    await _check_patient_access(patient_id, session, current_user)
    events = await service.list_for_patient(patient_id, limit=limit)
    events = await _safe_patient_events(events, patient_id, session)
    return PatientTimelineListResponse(
        patient_id=patient_id,
        events=[PatientTimelineEventResponse.model_validate(e) for e in events],
        count=len(events),
    )


@router.get(
    "/patients/{patient_id}/recent",
    response_model=PatientTimelineListResponse,
)
async def list_patient_timeline_recent(
    patient_id: uuid.UUID,
    service: PatientTimelineServiceDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = 50,
) -> PatientTimelineListResponse:
    await _check_patient_access(patient_id, session, current_user)
    events = await service.list_for_patient(patient_id, limit=limit)
    events = await _safe_patient_events(events, patient_id, session)
    return PatientTimelineListResponse(
        patient_id=patient_id,
        events=[PatientTimelineEventResponse.model_validate(e) for e in events],
        count=len(events),
    )


@router.delete("/events/{timeline_event_id}")
async def delete_timeline_event(
    timeline_event_id: uuid.UUID,
    session: SessionDep,
    repository: PatientTimelineRepositoryDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict[str, bool]:
    event = await repository.get_by_id(timeline_event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=_EVENT_NOT_FOUND)
    await _check_patient_access(event.patient_id, session, current_user)
    deleted = await repository.delete_by_id(timeline_event_id)
    if not deleted:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_EVENT_NOT_FOUND
        )
    await session.commit()
    return {"deleted": True}
