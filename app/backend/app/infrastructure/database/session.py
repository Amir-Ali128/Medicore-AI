"""Database engine, session factory, and FastAPI dependency.

Owns the singleton async engine and session factory and exposes `get_db`, an
async generator suitable for FastAPI dependency injection. Sessions are opened
per request, rolled back on error, and always closed.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.async_database_url,
    echo=_settings.db_echo,
    pool_pre_ping=_settings.db_pool_pre_ping,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    future=True,
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped `AsyncSession` (FastAPI dependency)."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
