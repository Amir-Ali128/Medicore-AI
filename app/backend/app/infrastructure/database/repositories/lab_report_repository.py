"""Repository for lab reports. Caller controls the transaction (no commit here)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.lab_report import LabReport


class LabReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def create(self, report: LabReport) -> LabReport:
        self._session.add(report)
        return report

    async def get_by_id(self, report_id: uuid.UUID) -> LabReport | None:
        return await self._session.get(LabReport, report_id)

    async def list_for_patient(self, patient_id: uuid.UUID) -> Sequence[LabReport]:
        stmt = (
            select(LabReport)
            .where(LabReport.patient_id == patient_id)
            .order_by(LabReport.report_date.desc().nulls_last(), LabReport.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def flush(self) -> None:
        await self._session.flush()
