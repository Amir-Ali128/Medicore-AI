"""Optional first-admin provisioning for deployments without a database shell.

Set both MEDICORE_ADMIN_NICKNAME and MEDICORE_ADMIN_PASSWORD in the backend
environment. The account is created only when that nickname does not exist.
Existing non-admin users are never silently elevated.
"""

from __future__ import annotations

import os
import re

from passlib.context import CryptContext
from sqlalchemy import select

from app.domain.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import AsyncSessionFactory

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_nickname_re = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


async def ensure_bootstrap_admin() -> str | None:
    nickname = os.getenv("MEDICORE_ADMIN_NICKNAME", "").strip().lower()
    password = os.getenv("MEDICORE_ADMIN_PASSWORD", "")

    if not nickname and not password:
        return None

    if not nickname or not password:
        print("Admin bootstrap skipped: both admin environment variables are required.")
        return None

    if not _nickname_re.fullmatch(nickname):
        print("Admin bootstrap skipped: MEDICORE_ADMIN_NICKNAME is invalid.")
        return None

    if len(password) < 12:
        print("Admin bootstrap skipped: MEDICORE_ADMIN_PASSWORD must be at least 12 characters.")
        return None

    async with AsyncSessionFactory() as session:
        existing = (
            await session.execute(select(User).where(User.nickname == nickname))
        ).scalar_one_or_none()

        if existing is not None:
            if existing.role != UserRole.ADMIN:
                print(
                    "Admin bootstrap skipped: nickname already belongs to a non-admin account; "
                    "no privilege escalation was performed."
                )
                return "conflict"
            return "exists"

        admin = User(
            nickname=nickname,
            email=None,
            full_name=None,
            role=UserRole.ADMIN,
            hashed_password=_pwd_context.hash(password),
            is_active=True,
            is_superuser=True,
        )
        session.add(admin)
        await session.commit()

    return "created"
