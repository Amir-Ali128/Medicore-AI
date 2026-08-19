"""User model — actors of the human review workflow."""

from __future__ import annotations

from sqlalchemy import Boolean, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import UserRole
from app.infrastructure.database.base import (
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    user_role_enum,
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Primary login identity. New individual accounts use only nickname + password.
    nickname: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )

    # Legacy / optional fields retained for existing institutional accounts and
    # backwards-compatible imports. New individual registration does not request them.
    email: Mapped[str | None] = mapped_column(
        String(320), unique=True, index=True, nullable=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255))

    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        user_role_enum,
        default=UserRole.VIEWER,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"<User id={self.id!s} nickname={self.nickname!r} "
            f"role={self.role.value}>"
        )
