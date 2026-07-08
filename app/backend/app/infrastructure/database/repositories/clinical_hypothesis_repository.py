"""Repository for clinical hypotheses. Caller controls the transaction."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis

PENDING_STATUS = "pending_review"


class ClinicalHypothesisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, hypothesis: ClinicalHypothesis) -> ClinicalHypothesis:
        self._session.add(hypothesis)
        return hypothesis

    async def get_by_id(
        self, hypothesis_id: uuid.UUID
    ) -> ClinicalHypothesis | None:
        return await self._session.get(ClinicalHypothesis, hypothesis_id)

    async def list_for_patient(
        self, patient_id: uuid.UUID
    ) -> Sequence[ClinicalHypothesis]:
        stmt = (
            select(ClinicalHypothesis)
            .where(ClinicalHypothesis.patient_id == patient_id)
            .order_by(ClinicalHypothesis.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_for_analysis_run(
        self, analysis_run_id: uuid.UUID
    ) -> Sequence[ClinicalHypothesis]:
        stmt = (
            select(ClinicalHypothesis)
            .where(ClinicalHypothesis.analysis_run_id == analysis_run_id)
            .order_by(ClinicalHypothesis.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_pending(self) -> Sequence[ClinicalHypothesis]:
        stmt = (
            select(ClinicalHypothesis)
            .where(ClinicalHypothesis.status == PENDING_STATUS)
            .order_by(ClinicalHypothesis.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    def update_status(
        self, hypothesis: ClinicalHypothesis, status: str
    ) -> ClinicalHypothesis:
        hypothesis.status = status
        return hypothesis

    async def flush(self) -> None:
        await self._session.flush()
