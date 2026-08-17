"""One-time migration for adding protocol numbers to existing patients.

Run from ``app/backend`` after deploying the model change:

    python scripts/add_patient_protocol_numbers.py

Fresh databases created with ``init_db.py`` already include the column.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text

from app.domain.patient_protocol import generate_protocol_no
from app.infrastructure.database import session as database_session


def _engine() -> Any:
    engine = (
        getattr(database_session, "async_engine", None)
        or getattr(database_session, "engine", None)
    )
    if engine is None:
        raise RuntimeError("Could not find SQLAlchemy async engine.")
    return engine


async def main() -> None:
    engine = _engine()

    async with engine.begin() as connection:
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

        patient_ids = (
            (
                await connection.execute(
                    text(
                        "SELECT id FROM patients "
                        "WHERE protocol_no IS NULL OR protocol_no = ''"
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
                {
                    "protocol_no": protocol_no,
                    "patient_id": patient_id,
                },
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

    await engine.dispose()
    print(
        "Patient protocol migration completed. "
        f"Backfilled {len(patient_ids)} patient(s)."
    )


if __name__ == "__main__":
    asyncio.run(main())
