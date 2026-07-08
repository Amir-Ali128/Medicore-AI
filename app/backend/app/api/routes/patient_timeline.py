"""Patient timeline routes.

Operational audit-trail endpoints. No diagnosis, no treatment advice, no Claude,
no clinical interpretation.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

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

router = APIRouter(prefix="/timeline", tags=["patient-timeline"])

_EVENT_NOT_FOUND = "Timeline event not found."


@router.post(
    "/events",
    response_model=PatientTimelineEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_timeline_event(
    payload: PatientTimelineEventCreate,
    session: SessionDep,
    service: PatientTimelineServiceDep,
) -> PatientTimelineEventResponse:
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
    "/events/{timeline_event_id}",
    response_model=PatientTimelineEventResponse,
)
async def get_timeline_event(
    timeline_event_id: uuid.UUID,
    repository: PatientTimelineRepositoryDep,
) -> PatientTimelineEventResponse:
    event = await repository.get_by_id(timeline_event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_EVENT_NOT_FOUND
        )
    return event


@router.get(
    "/patients/{patient_id}",
    response_model=PatientTimelineListResponse,
)
async def list_patient_timeline(
    patient_id: uuid.UUID,
    service: PatientTimelineServiceDep,
    limit: int | None = None,
) -> PatientTimelineListResponse:
    events = await service.list_for_patient(patient_id, limit=limit)
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
    limit: int = 50,
) -> PatientTimelineListResponse:
    events = await service.list_for_patient(patient_id, limit=limit)
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
) -> dict[str, bool]:
    deleted = await repository.delete_by_id(timeline_event_id)
    if not deleted:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_EVENT_NOT_FOUND
        )
    await session.commit()
    return {"deleted": True}
