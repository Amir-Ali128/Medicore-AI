"""Repository for parameter aliases.

Handles storage and resolution of raw-name -> canonical-parameter mappings.
`resolve` is the read path used later to map an incoming lab test name onto its
canonical parameter; it performs no numeric validation (no rule engine here).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.normalization import normalize_alias
from app.domain.normalization import normalize_alias
from app.infrastructure.database.models.parameter_alias import ParameterAlias

class ParameterAliasRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, alias_id: uuid.UUID) -> ParameterAlias | None:
        return await self._session.get(ParameterAlias, alias_id)

    async def exists(
        self, canonical_parameter_id: uuid.UUID, normalized_alias: str
    ) -> bool:
        stmt = select(ParameterAlias.id).where(
            ParameterAlias.canonical_parameter_id == canonical_parameter_id,
            ParameterAlias.normalized_alias == normalized_alias,
        )
        return (await self._session.execute(stmt)).first() is not None

    async def list_for_parameter(
        self, parameter_id: uuid.UUID
    ) -> Sequence[ParameterAlias]:
        stmt = select(ParameterAlias).where(
            ParameterAlias.canonical_parameter_id == parameter_id
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def find_by_normalized(
        self, normalized_alias: str
    ) -> Sequence[ParameterAlias]:
        stmt = (
            select(ParameterAlias)
            .where(ParameterAlias.normalized_alias == normalized_alias)
            .order_by(ParameterAlias.confidence.desc())
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def resolve(self, raw_name: str) -> ParameterAlias | None:
        """Return the highest-confidence alias matching `raw_name`, or None."""
        normalized = normalize_alias(raw_name)
        if not normalized:
            return None
        matches = await self.find_by_normalized(normalized)
        return matches[0] if matches else None

    def add(self, alias: ParameterAlias) -> ParameterAlias:
        self._session.add(alias)
        return alias

    async def add_unique(
        self,
        *,
        canonical_parameter_id: uuid.UUID,
        alias: str,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> ParameterAlias | None:
        """Add an alias unless (parameter, normalized_alias) already exists.

        Returns the created alias, or None if it was a duplicate.
        """
        normalized = normalize_alias(alias)
        if not normalized:
            return None
        if await self.exists(canonical_parameter_id, normalized):
            return None
        entity = ParameterAlias(
            canonical_parameter_id=canonical_parameter_id,
            alias=alias,
            normalized_alias=normalized,
            confidence=confidence,
            source=source,
        )
        self._session.add(entity)
        return entity

    async def flush(self) -> None:
        await self._session.flush()
