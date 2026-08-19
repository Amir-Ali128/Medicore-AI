"""Small idempotent database migrations that must run before the API serves traffic.

This module is intentionally narrow. It is not a replacement for Alembic; it
only protects deployments where shell access is unavailable by applying the
patient protocol-number change before request handlers can query ``patients``.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.patient_protocol import generate_protocol_no

# Transaction-scoped PostgreSQL advisory lock. It prevents two app workers from
# attempting the same startup migration at the same time.
_PATIENT_PROTOCOL_MIGRATION_LOCK = 4382026


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
