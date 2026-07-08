"""Repository for patient timeline events. Caller controls the transaction."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.patient_timeline_event import (
    PatientTimelineEvent,
)


class PatientTimelineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, event: PatientTimelineEvent) -> PatientTimelineEvent:
        self._session.add(event)
        return event

    async def get_by_id(
        self, event_id: uuid.UUID
    ) -> PatientTimelineEvent | None:
        return await self._session.get(PatientTimelineEvent, event_id)

    async def list_for_patient(
        self, patient_id: uuid.UUID
    ) -> Sequence[PatientTimelineEvent]:
        stmt = (
            select(PatientTimelineEvent)
            .where(PatientTimelineEvent.patient_id == patient_id)
            .order_by(
                PatientTimelineEvent.occurred_at.desc(),
                PatientTimelineEvent.created_at.desc(),
            )
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_recent_for_patient(
        self, patient_id: uuid.UUID, limit: int = 50
    ) -> Sequence[PatientTimelineEvent]:
        stmt = (
            select(PatientTimelineEvent)
            .where(PatientTimelineEvent.patient_id == patient_id)
            .order_by(
                PatientTimelineEvent.occurred_at.desc(),
                PatientTimelineEvent.created_at.desc(),
            )
            .limit(limit)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_by_source_entity(
        self,
        patient_id: uuid.UUID,
        source_entity_type: str,
        source_entity_id: uuid.UUID,
        event_type: str | None = None,
    ) -> Sequence[PatientTimelineEvent]:
        conditions = [
            PatientTimelineEvent.patient_id == patient_id,
            PatientTimelineEvent.source_entity_type == source_entity_type,
            PatientTimelineEvent.source_entity_id == source_entity_id,
        ]
        if event_type is not None:
            conditions.append(PatientTimelineEvent.event_type == event_type)
        stmt = (
            select(PatientTimelineEvent)
            .where(*conditions)
            .order_by(PatientTimelineEvent.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def delete_by_id(self, event_id: uuid.UUID) -> bool:
        event = await self.get_by_id(event_id)
        if event is None:
            return False
        await self._session.delete(event)
        return True

    async def flush(self) -> None:
        await self._session.flush()
