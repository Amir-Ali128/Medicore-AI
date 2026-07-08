"""Repository for extracted lab values. Caller controls the transaction."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.extracted_lab_value import ExtractedLabValue


class ExtractedLabValueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create_many(
        self, values: list[ExtractedLabValue]
    ) -> list[ExtractedLabValue]:
        self._session.add_all(values)
        return values

    async def get_by_id(
        self, value_id: uuid.UUID
    ) -> ExtractedLabValue | None:
        return await self._session.get(ExtractedLabValue, value_id)

    async def list_for_job(
        self, extraction_job_id: uuid.UUID
    ) -> Sequence[ExtractedLabValue]:
        stmt = (
            select(ExtractedLabValue)
            .where(ExtractedLabValue.extraction_job_id == extraction_job_id)
            .order_by(ExtractedLabValue.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    def update(
        self, value: ExtractedLabValue, changes: dict[str, Any]
    ) -> ExtractedLabValue:
        for field, new_value in changes.items():
            setattr(value, field, new_value)
        return value

    async def flush(self) -> None:
        await self._session.flush()
