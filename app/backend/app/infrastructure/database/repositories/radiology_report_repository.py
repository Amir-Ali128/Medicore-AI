"""Repository for Phase 2 radiology reports; callers own transactions."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.radiology_report import RadiologyReport


class RadiologyReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, report: RadiologyReport) -> RadiologyReport:
        self._session.add(report)
        return report

    async def get_by_id(self, report_id: uuid.UUID) -> RadiologyReport | None:
        return await self._session.get(RadiologyReport, report_id)

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, limit: int = 50
    ) -> Sequence[RadiologyReport]:
        stmt = (
            select(RadiologyReport)
            .where(RadiologyReport.patient_id == patient_id)
            .order_by(
                RadiologyReport.report_date.desc().nulls_last(),
                RadiologyReport.created_at.desc(),
            )
            .limit(limit)
        )
        return (await self._session.execute(stmt)).scalars().all()
