"""Small idempotent database migrations that must run before the API serves traffic.

These narrow migrations protect deployments where shell access is unavailable.
They are intentionally small and are not a replacement for Alembic.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.patient_protocol import generate_protocol_no

# Transaction-scoped PostgreSQL advisory locks prevent concurrent workers from
# attempting the same startup migration at the same time.
_PATIENT_PROTOCOL_MIGRATION_LOCK = 4382026
_USER_NICKNAME_MIGRATION_LOCK = 4382027
_ANALYTICS_PRESENCE_MIGRATION_LOCK = 4382028


def _legacy_nickname_candidate(email: str | None, full_name: str | None, user_id: object) -> str:
    source = (email or "").split("@", 1)[0] or (full_name or "") or "user"
    candidate = re.sub(r"[^a-zA-Z0-9._-]+", "-", source.strip().lower()).strip("-._")
    if len(candidate) < 3:
        candidate = f"user-{str(user_id)[:8]}"
    return candidate[:48]


async def ensure_user_nicknames(engine: AsyncEngine) -> int:
    """Add/backfill the nickname login identity for existing user rows.

    Existing email-based accounts receive a deterministic nickname based on the
    email local-part (for example doctor@medicore.ai -> doctor). New accounts can
    then omit email/full_name entirely. The operation is idempotent.
    """

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _USER_NICKNAME_MIGRATION_LOCK},
        )

        users_table = (
            await connection.execute(text("SELECT to_regclass('public.users')"))
        ).scalar_one_or_none()
        if users_table is None:
            return 0

        await connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS nickname VARCHAR(64)")
        )

        existing_nicknames = set(
            value.lower()
            for value in (
                (
                    await connection.execute(
                        text(
                            "SELECT nickname FROM users "
                            "WHERE nickname IS NOT NULL AND nickname <> ''"
                        )
                    )
                )
                .scalars()
                .all()
            )
        )

        rows = (
            await connection.execute(
                text(
                    "SELECT id, email, full_name FROM users "
                    "WHERE nickname IS NULL OR nickname = '' ORDER BY id"
                )
            )
        ).all()

        for user_id, email, full_name in rows:
            base = _legacy_nickname_candidate(email, full_name, user_id)
            nickname = base
            suffix = 2
            while nickname.lower() in existing_nicknames:
                tail = f"-{suffix}"
                nickname = f"{base[:64 - len(tail)]}{tail}"
                suffix += 1

            await connection.execute(
                text("UPDATE users SET nickname = :nickname WHERE id = :user_id"),
                {"nickname": nickname, "user_id": user_id},
            )
            existing_nicknames.add(nickname.lower())

        await connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_nickname "
                "ON users (nickname)"
            )
        )
        await connection.execute(
            text("ALTER TABLE users ALTER COLUMN nickname SET NOT NULL")
        )
        # Email is retained only as optional legacy/institutional metadata.
        await connection.execute(
            text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL")
        )

    return len(rows)


async def ensure_patient_protocol_numbers(engine: AsyncEngine) -> int:
    """Ensure every existing patient has a unique, non-null protocol number.

    Returns the number of patient rows backfilled. The operation is idempotent:
    after the first successful run, later startups only verify the schema and
    return zero.
    """

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _PATIENT_PROTOCOL_MIGRATION_LOCK},
        )

        patients_table = (
            await connection.execute(text("SELECT to_regclass('public.patients')"))
        ).scalar_one_or_none()
        if patients_table is None:
            # Fresh/dev databases are still created explicitly by init_db.py.
            return 0

        await connection.execute(
            text(
                "ALTER TABLE patients "
                "ADD COLUMN IF NOT EXISTS protocol_no VARCHAR(32)"
            )
        )

        existing_numbers = set(
            (
                await connection.execute(
                    text(
                        "SELECT protocol_no FROM patients "
                        "WHERE protocol_no IS NOT NULL AND protocol_no <> ''"
                    )
                )
            )
            .scalars()
            .all()
        )

        patient_ids = list(
            (
                await connection.execute(
                    text(
                        "SELECT id FROM patients "
                        "WHERE protocol_no IS NULL OR protocol_no = '' "
                        "ORDER BY id"
                    )
                )
            )
            .scalars()
            .all()
        )

        for patient_id in patient_ids:
            protocol_no = generate_protocol_no()
            while protocol_no in existing_numbers:
                protocol_no = generate_protocol_no()

            await connection.execute(
                text(
                    "UPDATE patients "
                    "SET protocol_no = :protocol_no "
                    "WHERE id = :patient_id"
                ),
                {"protocol_no": protocol_no, "patient_id": patient_id},
            )
            existing_numbers.add(protocol_no)

        await connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_patients_protocol_no "
                "ON patients (protocol_no)"
            )
        )
        await connection.execute(
            text(
                "ALTER TABLE patients "
                "ALTER COLUMN protocol_no SET NOT NULL"
            )
        )

    return len(patient_ids)


async def ensure_analytics_presence(engine: AsyncEngine) -> None:
    """Create or extend the small presence table used by the admin live-traffic view."""

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _ANALYTICS_PRESENCE_MIGRATION_LOCK},
        )

        await connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analytics_presence (
                    id UUID PRIMARY KEY,
                    visitor_id VARCHAR(64) NOT NULL UNIQUE,
                    user_id UUID NULL,
                    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_path VARCHAR(512) NULL,
                    ip_address VARCHAR(64) NULL,
                    ip_hash VARCHAR(64) NULL,
                    country_code VARCHAR(8) NULL,
                    country VARCHAR(128) NULL,
                    region VARCHAR(128) NULL,
                    city VARCHAR(128) NULL,
                    latitude DOUBLE PRECISION NULL,
                    longitude DOUBLE PRECISION NULL,
                    user_agent VARCHAR(512) NULL,
                    timezone VARCHAR(128) NULL,
                    language VARCHAR(64) NULL,
                    platform VARCHAR(128) NULL,
                    device_brand VARCHAR(128) NULL,
                    device_model VARCHAR(192) NULL,
                    device_type VARCHAR(32) NULL,
                    os_name VARCHAR(128) NULL,
                    os_version VARCHAR(128) NULL,
                    browser_name VARCHAR(128) NULL,
                    browser_version VARCHAR(128) NULL,
                    architecture VARCHAR(64) NULL,
                    request_count INTEGER NOT NULL DEFAULT 1
                )
                """
            )
        )

        # Existing deployments already have the table, so add new columns
        # idempotently instead of relying on CREATE TABLE IF NOT EXISTS.
        for statement in (
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS device_brand VARCHAR(128)",
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS device_model VARCHAR(192)",
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS device_type VARCHAR(32)",
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS os_name VARCHAR(128)",
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS os_version VARCHAR(128)",
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS browser_name VARCHAR(128)",
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS browser_version VARCHAR(128)",
            "ALTER TABLE analytics_presence ADD COLUMN IF NOT EXISTS architecture VARCHAR(64)",
        ):
            await connection.execute(text(statement))

        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_analytics_presence_last_seen "
                "ON analytics_presence (last_seen_at DESC)"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_analytics_presence_user_id "
                "ON analytics_presence (user_id)"
            )
        )
        await connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_analytics_presence_ip_hash "
                "ON analytics_presence (ip_hash)"
            )
        )


async def purge_old_analytics(engine: AsyncEngine) -> int:
    """Purge presence rows older than the configured retention window at startup."""

    try:
        retention_days = max(1, int(os.getenv("ANALYTICS_RETENTION_DAYS", "30")))
    except ValueError:
        retention_days = 30

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)

    async with engine.begin() as connection:
        table = (
            await connection.execute(text("SELECT to_regclass('public.analytics_presence')"))
        ).scalar_one_or_none()
        if table is None:
            return 0

        result = await connection.execute(
            text("DELETE FROM analytics_presence WHERE last_seen_at < :cutoff"),
            {"cutoff": cutoff},
        )
        return int(result.rowcount or 0)
