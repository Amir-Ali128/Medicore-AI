"""Repository for doctor reviews. Caller controls the transaction."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.doctor_review import DoctorReview


class DoctorReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, review: DoctorReview) -> DoctorReview:
        self._session.add(review)
        return review

    async def get_by_id(self, review_id: uuid.UUID) -> DoctorReview | None:
        return await self._session.get(DoctorReview, review_id)

    async def list_for_hypothesis(
        self, clinical_hypothesis_id: uuid.UUID
    ) -> Sequence[DoctorReview]:
        stmt = (
            select(DoctorReview)
            .where(DoctorReview.clinical_hypothesis_id == clinical_hypothesis_id)
            .order_by(DoctorReview.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def flush(self) -> None:
        await self._session.flush()
