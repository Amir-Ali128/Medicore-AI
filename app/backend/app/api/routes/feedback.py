"""Privacy-conscious product feedback routes.

Individual users can submit product suggestions/bug reports without including
clinical data. Admins can review and update the status of submissions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.routes.auth import get_current_active_user, require_roles
from app.domain.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import AsyncSessionFactory

router = APIRouter(prefix="/feedback", tags=["feedback"])

FeedbackCategory = Literal["suggestion", "bug", "usability", "other"]
FeedbackStatus = Literal["new", "read", "resolved"]


class FeedbackCreate(BaseModel):
    category: FeedbackCategory = "suggestion"
    subject: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=10, max_length=2000)


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus


class FeedbackOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    nickname: str | None
    category: str
    subject: str
    message: str
    status: str
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> FeedbackOut:
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Geri bildirim formu bireysel kullanıcı hesapları içindir.",
        )

    feedback_id = uuid.uuid4()
    async with AsyncSessionFactory() as session:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO user_feedback (
                        id, user_id, category, subject, message, status,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, :user_id, :category, :subject, :message, 'new',
                        NOW(), NOW()
                    )
                    RETURNING id, user_id, category, subject, message, status,
                              created_at, updated_at
                    """
                ),
                {
                    "id": feedback_id,
                    "user_id": current_user.id,
                    "category": payload.category,
                    "subject": payload.subject.strip(),
                    "message": payload.message.strip(),
                },
            )
        ).mappings().one()
        await session.commit()

    return FeedbackOut(**row, nickname=current_user.nickname)


@router.get("/mine", response_model=list[FeedbackOut])
async def my_feedback(
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[FeedbackOut]:
    if current_user.role != UserRole.PATIENT:
        raise HTTPException(status_code=403, detail="Bireysel kullanıcı erişimi gerekir.")

    async with AsyncSessionFactory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, user_id, category, subject, message, status,
                           created_at, updated_at
                    FROM user_feedback
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"user_id": current_user.id, "limit": limit},
            )
        ).mappings().all()

    return [FeedbackOut(**row, nickname=current_user.nickname) for row in rows]


@router.get("/admin", response_model=list[FeedbackOut])
async def admin_feedback(
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    limit: int = Query(default=200, ge=1, le=500),
) -> list[FeedbackOut]:
    async with AsyncSessionFactory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT f.id, f.user_id, u.nickname, f.category, f.subject,
                           f.message, f.status, f.created_at, f.updated_at
                    FROM user_feedback AS f
                    LEFT JOIN users AS u ON u.id = f.user_id
                    ORDER BY
                        CASE f.status WHEN 'new' THEN 0 WHEN 'read' THEN 1 ELSE 2 END,
                        f.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
        ).mappings().all()

    return [FeedbackOut(**row) for row in rows]


@router.patch("/admin/{feedback_id}", response_model=FeedbackOut)
async def update_feedback_status(
    feedback_id: uuid.UUID,
    payload: FeedbackStatusUpdate,
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> FeedbackOut:
    async with AsyncSessionFactory() as session:
        row = (
            await session.execute(
                text(
                    """
                    UPDATE user_feedback
                    SET status = :status, updated_at = NOW()
                    WHERE id = :id
                    RETURNING id, user_id, category, subject, message, status,
                              created_at, updated_at
                    """
                ),
                {"id": feedback_id, "status": payload.status},
            )
        ).mappings().one_or_none()

        if row is None:
            raise HTTPException(status_code=404, detail="Geri bildirim bulunamadı.")

        nickname = (
            await session.execute(
                text("SELECT nickname FROM users WHERE id = :user_id"),
                {"user_id": row["user_id"]},
            )
        ).scalar_one_or_none()
        await session.commit()

    return FeedbackOut(**row, nickname=nickname)
