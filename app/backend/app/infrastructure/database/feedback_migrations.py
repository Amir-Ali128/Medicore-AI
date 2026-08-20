"""Small startup migration for product feedback submissions."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_FEEDBACK_MIGRATION_LOCK = 4382029


async def ensure_user_feedback(engine: AsyncEngine) -> None:
    """Create the feedback inbox table idempotently."""

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _FEEDBACK_MIGRATION_LOCK},
        )
        await connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id UUID PRIMARY KEY,
                    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
                    category VARCHAR(32) NOT NULL,
                    subject VARCHAR(120) NOT NULL,
                    message VARCHAR(2000) NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'new',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_feedback_created_at "
                "ON user_feedback (created_at DESC)"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_feedback_status "
                "ON user_feedback (status, created_at DESC)"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_feedback_user_id "
                "ON user_feedback (user_id, created_at DESC)"
            )
        )
