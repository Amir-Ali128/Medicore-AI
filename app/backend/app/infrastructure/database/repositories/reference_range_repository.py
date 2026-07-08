"""Repository for reference ranges.

Stores and retrieves demographic-scoped normal ranges. `find_applicable` selects
the reference band(s) that fit a demographic profile — a pure data query that
prepares input for future rule-based numeric validation, without performing any
evaluation itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import Sex
from app.infrastructure.database.models.reference_range import ReferenceRange


class ReferenceRangeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, range_id: uuid.UUID) -> ReferenceRange | None:
        return await self._session.get(ReferenceRange, range_id)

    async def list_for_parameter(
        self, parameter_id: uuid.UUID
    ) -> Sequence[ReferenceRange]:
        stmt = select(ReferenceRange).where(
            ReferenceRange.parameter_id == parameter_id
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def delete_for_parameter(self, parameter_id: uuid.UUID) -> None:
        """Remove all ranges for a parameter (used for clean re-import)."""
        await self._session.execute(
            delete(ReferenceRange).where(
                ReferenceRange.parameter_id == parameter_id
            )
        )

    def add(self, reference_range: ReferenceRange) -> ReferenceRange:
        self._session.add(reference_range)
        return reference_range

    async def find_applicable(
        self,
        parameter_id: uuid.UUID,
        *,
        sex: Sex | None = None,
        age: float | None = None,
        pregnant: bool | None = None,
    ) -> Sequence[ReferenceRange]:
        """Return candidate ranges matching the given demographic profile.

        A NULL bound on a stored range is treated as open-ended. `sex=ANY`
        ranges always qualify. This method filters only; it does not compare a
        measured value against the range.
        """
        conditions = [ReferenceRange.parameter_id == parameter_id]

        if sex is not None:
            conditions.append(
                or_(ReferenceRange.sex == sex, ReferenceRange.sex == Sex.ANY)
            )
        if age is not None:
            conditions.append(
                or_(ReferenceRange.age_min.is_(None), ReferenceRange.age_min <= age)
            )
            conditions.append(
                or_(ReferenceRange.age_max.is_(None), ReferenceRange.age_max >= age)
            )
        if pregnant is not None:
            conditions.append(
                or_(
                    ReferenceRange.pregnancy_status.is_(None),
                    ReferenceRange.pregnancy_status == pregnant,
                )
            )

        stmt = select(ReferenceRange).where(*conditions)
        return (await self._session.execute(stmt)).scalars().all()

    async def flush(self) -> None:
        await self._session.flush()
