"""Repository for extraction jobs. Caller controls the transaction."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.extraction_job import ExtractionJob

PENDING_STATUS = "pending_review"


class ExtractionJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, job: ExtractionJob) -> ExtractionJob:
        self._session.add(job)
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> ExtractionJob | None:
        return await self._session.get(ExtractionJob, job_id)

    async def list_for_patient(
        self, patient_id: uuid.UUID
    ) -> Sequence[ExtractionJob]:
        stmt = (
            select(ExtractionJob)
            .where(ExtractionJob.patient_id == patient_id)
            .order_by(ExtractionJob.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_pending(self) -> Sequence[ExtractionJob]:
        stmt = (
            select(ExtractionJob)
            .where(ExtractionJob.status == PENDING_STATUS)
            .order_by(ExtractionJob.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    def update_status(self, job: ExtractionJob, status: str) -> ExtractionJob:
        job.status = status
        return job

    async def flush(self) -> None:
        await self._session.flush()
