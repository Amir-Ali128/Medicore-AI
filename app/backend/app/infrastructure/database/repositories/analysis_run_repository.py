"""Repository for analysis runs. Caller controls the transaction (no commit here)."""


from __future__ import annotations


import uuid
from collections.abc import Sequence
from datetime import datetime, timezone


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.infrastructure.database.models.analysis_run import AnalysisRun




class AnalysisRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session


    def create(self, run: AnalysisRun) -> AnalysisRun:
        self._session.add(run)
        return run


    async def get_by_id(self, run_id: uuid.UUID) -> AnalysisRun | None:
        return await self._session.get(AnalysisRun, run_id)


    async def list_for_report(
        self, lab_report_id: uuid.UUID
    ) -> Sequence[AnalysisRun]:
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.lab_report_id == lab_report_id)
            .order_by(AnalysisRun.created_at.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()


    def update_counts(
        self,
        run: AnalysisRun,
        *,
        total: int,
        normal: int,
        low: int,
        high: int,
        needs_review: int,
        unknown: int,
    ) -> AnalysisRun:
        run.total_results = total
        run.normal_count = normal
        run.low_count = low
        run.high_count = high
        run.needs_review_count = needs_review
        run.unknown_count = unknown
        return run


    def mark_completed(
        self, run: AnalysisRun, *, status: str = "completed"
    ) -> AnalysisRun:
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        return run


    async def flush(self) -> None:
        await self._session.flush()



















































