"""Create all database tables for local/dev use.

Registers every model (via the models package) and issues CREATE TABLE for the
whole metadata. Does not drop, seed, or print any secrets/URLs.

Run:  python -m app.scripts.create_dev_tables
"""

from __future__ import annotations

import asyncio

# Importing the models package registers all tables on Base.metadata.
import app.infrastructure.database.models  # noqa: F401
from app.infrastructure.database.base import Base
from app.infrastructure.database.session import engine


async def _create() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Dev tables created successfully.")
    await engine.dispose()


def main() -> None:
    asyncio.run(_create())


if __name__ == "__main__":
    main()
