"""Repository for lab results. Caller controls the transaction (no commit here)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.lab_result import LabResult


class LabResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, result: LabResult) -> LabResult:
        self._session.add(result)
        return result

    def create_many(self, results: list[LabResult]) -> list[LabResult]:
        self._session.add_all(results)
        return results

    async def get_by_id(self, result_id: uuid.UUID) -> LabResult | None:
        return await self._session.get(LabResult, result_id)

    async def list_for_report(self, lab_report_id: uuid.UUID) -> Sequence[LabResult]:
        stmt = (
            select(LabResult)
            .where(LabResult.lab_report_id == lab_report_id)
            .order_by(LabResult.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_for_analysis_run(
        self, analysis_run_id: uuid.UUID
    ) -> Sequence[LabResult]:
        stmt = (
            select(LabResult)
            .where(LabResult.analysis_run_id == analysis_run_id)
            .order_by(LabResult.created_at.asc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def latest_previous_result(
        self,
        patient_id: uuid.UUID,
        parameter_id: uuid.UUID,
        *,
        before_date: date | None = None,
        exclude_result_id: uuid.UUID | None = None,
    ) -> LabResult | None:
        """Most recent prior result for the same patient + canonical parameter.

        Excludes the current result (if given), optionally restricts to results
        measured before `before_date`, and orders by measured_at desc (nulls
        last) then created_at desc. Returns one LabResult or None.
        """
        stmt = select(LabResult).where(
            LabResult.patient_id == patient_id,
            LabResult.parameter_id == parameter_id,
        )
        if exclude_result_id is not None:
            stmt = stmt.where(LabResult.id != exclude_result_id)
        if before_date is not None:
            stmt = stmt.where(LabResult.measured_at < before_date)

        stmt = stmt.order_by(
            LabResult.measured_at.desc().nulls_last(),
            LabResult.created_at.desc(),
        ).limit(1)

        return (await self._session.execute(stmt)).scalars().first()

    async def flush(self) -> None:
        await self._session.flush()
