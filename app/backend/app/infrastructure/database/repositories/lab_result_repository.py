"""Repository for lab results. Caller controls the transaction (no commit here)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ResultStatus
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

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        *,
        limit: int = 250,
    ) -> Sequence[LabResult]:
        safe_limit = max(1, min(int(limit), 1000))
        stmt = (
            select(LabResult)
            .where(LabResult.patient_id == patient_id)
            .order_by(
                LabResult.measured_at.desc().nulls_last(),
                LabResult.created_at.desc(),
            )
            .limit(safe_limit)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_review_queue_for_patient(
        self,
        patient_id: uuid.UUID,
        *,
        limit: int = 250,
    ) -> Sequence[LabResult]:
        safe_limit = max(1, min(int(limit), 1000))
        stmt = (
            select(LabResult)
            .where(
                LabResult.patient_id == patient_id,
                LabResult.needs_review.is_(True),
            )
            .order_by(
                LabResult.measured_at.desc().nulls_last(),
                LabResult.created_at.desc(),
            )
            .limit(safe_limit)
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
        """Most recent prior result for the same patient + canonical parameter."""
        return await self.latest_previous_match(
            patient_id,
            parameter_id=parameter_id,
            before_date=before_date,
            exclude_result_id=exclude_result_id,
            trusted_only=False,
        )

    async def latest_previous_match(
        self,
        patient_id: uuid.UUID,
        *,
        parameter_id: uuid.UUID | None = None,
        parameter_code: str | None = None,
        canonical_name: str | None = None,
        raw_parameter_name: str | None = None,
        before_date: date | None = None,
        exclude_result_id: uuid.UUID | None = None,
        trusted_only: bool = True,
    ) -> LabResult | None:
        """Resolve the most recent comparable historical result.

        Identity priority is parameter_id -> parameter_code -> canonical/raw name.
        For the seven-source native pipeline, parameter_id can legitimately be absent;
        the stable persisted parameter_code created by the history bridge is then used.
        Trusted-only lookup excludes previous review rows from longitudinal evidence.
        """
        stmt = select(LabResult).where(LabResult.patient_id == patient_id)

        if parameter_id is not None:
            stmt = stmt.where(LabResult.parameter_id == parameter_id)
        elif parameter_code:
            stmt = stmt.where(LabResult.parameter_code == parameter_code)
        elif canonical_name or raw_parameter_name:
            identities = []
            if canonical_name:
                identities.append(LabResult.canonical_name == canonical_name)
            if raw_parameter_name:
                identities.append(LabResult.raw_parameter_name == raw_parameter_name)
            stmt = stmt.where(or_(*identities))
        else:
            return None

        if trusted_only:
            stmt = stmt.where(
                LabResult.needs_review.is_(False),
                LabResult.result_status.in_(
                    [ResultStatus.NORMAL, ResultStatus.LOW, ResultStatus.HIGH]
                ),
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
