"""Optional manual runner for the patient protocol-number migration.

Render deployments do not need shell access: the same idempotent migration runs
automatically in the FastAPI lifespan before the API starts serving requests.

This script is kept for local/dev/admin use:

    python scripts/add_patient_protocol_numbers.py
"""

from __future__ import annotations

import asyncio

from app.infrastructure.database.session import engine
from app.infrastructure.database.startup_migrations import (
    ensure_patient_protocol_numbers,
)


async def main() -> None:
    backfilled = await ensure_patient_protocol_numbers(engine)
    await engine.dispose()
    print(
        "Patient protocol migration completed. "
        f"Backfilled {backfilled} patient(s)."
    )


if __name__ == "__main__":
    asyncio.run(main())
