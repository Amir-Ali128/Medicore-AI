"""Repository for canonical clinical parameters.

Encapsulates all persistence access for `ClinicalParameter`. Transaction control
(commit/rollback) is intentionally left to the caller / unit-of-work so the
repository stays composable and side-effect predictable.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.clinical_parameter import ClinicalParameter


class ClinicalParameterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, parameter_id: uuid.UUID) -> ClinicalParameter | None:
        return await self._session.get(ClinicalParameter, parameter_id)

    async def get_by_code(self, parameter_code: str) -> ClinicalParameter | None:
        stmt = select(ClinicalParameter).where(
            ClinicalParameter.parameter_code == parameter_code
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> Sequence[ClinicalParameter]:
        stmt = select(ClinicalParameter).order_by(ClinicalParameter.canonical_name)
        return (await self._session.execute(stmt)).scalars().all()

    async def list_active_phase1(self) -> Sequence[ClinicalParameter]:
        stmt = (
            select(ClinicalParameter)
            .where(ClinicalParameter.active_phase1.is_(True))
            .order_by(ClinicalParameter.category, ClinicalParameter.canonical_name)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_by_category(self, category: str) -> Sequence[ClinicalParameter]:
        stmt = (
            select(ClinicalParameter)
            .where(ClinicalParameter.category == category)
            .order_by(ClinicalParameter.canonical_name)
        )
        return (await self._session.execute(stmt)).scalars().all()

    def add(self, parameter: ClinicalParameter) -> ClinicalParameter:
        self._session.add(parameter)
        return parameter

    async def upsert_by_code(
        self, *, parameter_code: str, values: dict[str, Any]
    ) -> tuple[ClinicalParameter, bool]:
        """Create the parameter, or update it in place if the code exists.

        Returns `(parameter, created)`. `parameter_code` itself is never
        overwritten by `values`.
        """
        existing = await self.get_by_code(parameter_code)
        if existing is None:
            parameter = ClinicalParameter(parameter_code=parameter_code, **values)
            self._session.add(parameter)
            return parameter, True

        for key, value in values.items():
            if key == "parameter_code":
                continue
            setattr(existing, key, value)
        return existing, False

    async def flush(self) -> None:
        await self._session.flush()
