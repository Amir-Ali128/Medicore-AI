from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.infrastructure.database import session


DEMO_EMAIL = "doctor@medicore.ai"
DEMO_PASSWORD = "demo123"


async def main():
    engine = getattr(session, "async_engine", None) or getattr(session, "engine", None)

    if engine is None:
        raise RuntimeError("Database engine bulunamadı.")

    hashed_password = hash_password(DEMO_PASSWORD)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE users
                SET hashed_password = :hashed_password,
                    is_active = true,
                    updated_at = NOW()
                WHERE email = :email
                """
            ),
            {
                "email": DEMO_EMAIL,
                "hashed_password": hashed_password,
            },
        )

    await engine.dispose()

    print("Demo user password updated.")
    print(f"Email: {DEMO_EMAIL}")
    print(f"Password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())