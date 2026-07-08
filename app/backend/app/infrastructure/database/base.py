"""Declarative base and shared model mixins.

Defines the single `Base` used by every ORM model (so they share one metadata
registry and can resolve string-based relationships), plus reusable mixins for
UUID primary keys and audit timestamps. A naming convention is attached to the
metadata so Alembic autogeneration produces deterministic, portable constraint
names.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.enums import (
    AnalysisLevel,
    ResultStatus,
    ReviewAction,
    Sex,
    TrendStatus,
    UserRole,
    enum_values,
)

# Deterministic constraint/index names — critical for stable Alembic diffs.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Root declarative base shared by all persistence models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _pg_enum(enum_cls: type, name: str) -> SAEnum:
    """Build a native PostgreSQL ENUM bound to the shared metadata.

    Binding to `Base.metadata` and reusing a single instance across columns
    ensures the type is emitted exactly once, even when several tables
    reference it (e.g. `sex` on both patients and reference_ranges).
    """
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=enum_values,
        metadata=Base.metadata,
    )


# Shared enum types actually mapped by Phase 1 models.
user_role_enum: SAEnum = _pg_enum(UserRole, "user_role")
analysis_level_enum: SAEnum = _pg_enum(AnalysisLevel, "analysis_level")
sex_enum: SAEnum = _pg_enum(Sex, "sex")
result_status_enum: SAEnum = _pg_enum(ResultStatus, "result_status")
trend_status_enum: SAEnum = _pg_enum(TrendStatus, "trend_status")
review_action_enum: SAEnum = _pg_enum(ReviewAction, "review_action")


class UUIDPrimaryKeyMixin:
    """Adds a client-generated UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Adds database-managed audit timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
