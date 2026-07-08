"""PatientTimelineService.

Records patient-related operational events in chronological order. It performs
no diagnosis, no treatment advice, no Claude calls, and never commits (the route
owns the transaction).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.infrastructure.database.models.patient_timeline_event import (
    PatientTimelineEvent,
)
from app.infrastructure.database.repositories.patient_timeline_repository import (
    PatientTimelineRepository,
)
from app.schemas.patient_timeline import PatientTimelineEventCreate


class PatientTimelineService:
    def __init__(
        self, patient_timeline_repository: PatientTimelineRepository
    ) -> None:
        self._timeline = patient_timeline_repository

    async def create_event(
        self, payload: PatientTimelineEventCreate
    ) -> PatientTimelineEvent:
        event = self._to_model(payload)
        self._timeline.create(event)
        await self._timeline.flush()
        return event

    async def list_for_patient(
        self, patient_id: uuid.UUID, limit: int | None = None
    ) -> list[PatientTimelineEvent]:
        if limit is not None:
            events = await self._timeline.list_recent_for_patient(patient_id, limit)
        else:
            events = await self._timeline.list_for_patient(patient_id)
        return list(events)

    async def create_event_if_not_exists_for_source(
        self, payload: PatientTimelineEventCreate
    ) -> PatientTimelineEvent | None:
        """Idempotent create keyed by (patient, source entity, event_type).

        Prevents duplicate timeline entries when future modules emit the same
        event repeatedly. Falls back to a plain create when no source entity is
        provided.
        """
        if payload.source_entity_type is not None and payload.source_entity_id is not None:
            existing = await self._timeline.list_by_source_entity(
                patient_id=payload.patient_id,
                source_entity_type=payload.source_entity_type,
                source_entity_id=payload.source_entity_id,
                event_type=payload.event_type,
            )
            if existing:
                return None

        return await self.create_event(payload)

    @staticmethod
    def _to_model(payload: PatientTimelineEventCreate) -> PatientTimelineEvent:
        occurred_at = payload.occurred_at or datetime.now(timezone.utc)
        return PatientTimelineEvent(
            patient_id=payload.patient_id,
            event_type=payload.event_type,
            status=payload.status,
            title=payload.title,
            description=payload.description,
            occurred_at=occurred_at,
            source=payload.source,
            source_entity_type=payload.source_entity_type,
            source_entity_id=payload.source_entity_id,
            actor_user_id=payload.actor_user_id,
            lab_report_id=payload.lab_report_id,
            analysis_run_id=payload.analysis_run_id,
            clinical_hypothesis_id=payload.clinical_hypothesis_id,
            doctor_review_id=payload.doctor_review_id,
            extraction_job_id=payload.extraction_job_id,
            metadata_json=dict(payload.metadata_json),
        )
