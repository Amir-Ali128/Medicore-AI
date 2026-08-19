"""Authentication routes for MediCore AI.

Public individual registration uses only nickname + password. Institutional
accounts are provisioned separately and authenticate with nickname + password.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import AsyncSessionFactory

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

_NICKNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
InstitutionType = Literal["individual", "institutional"]


def _normalize_nickname(value: str) -> str:
    return value.strip().lower()


def _validate_nickname(value: str) -> str:
    nickname = _normalize_nickname(value)
    if not _NICKNAME_RE.fullmatch(nickname):
        raise ValueError(
            "Rumuz 3-32 karakter olmalı; küçük/büyük harf, rakam, nokta, "
            "alt çizgi veya tire kullanılabilir."
        )
    return nickname


class RegisterRequest(BaseModel):
    nickname: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        return _validate_nickname(value)


class LoginRequest(BaseModel):
    nickname: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    account_type: InstitutionType = "individual"

    @field_validator("nickname")
    @classmethod
    def normalize_nickname(cls, value: str) -> str:
        return _validate_nickname(value)


class UserOut(BaseModel):
    id: uuid.UUID
    nickname: str
    role: UserRole
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _validate_password(password: str) -> None:
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Şifre en az 6 karakter olmalı.",
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    *,
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        nickname=user.nickname,
        role=user.role,
        is_active=user.is_active,
    )


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(subject=str(user.id), role=str(user.role))
    return TokenResponse(access_token=token, user=_user_out(user))


async def _get_user_by_nickname(nickname: str) -> User | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.nickname == nickname))
        return result.scalar_one_or_none()


async def _authenticate_user(nickname: str, password: str) -> User:
    normalized_nickname = _normalize_nickname(nickname)
    user = await _get_user_by_nickname(normalized_nickname)

    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Rumuz veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu kullanıcı pasif durumda.",
        )

    return user


def _validate_account_type(user: User, account_type: InstitutionType) -> None:
    institutional_roles = {
        UserRole.DOCTOR,
        UserRole.LAB_STAFF,
        UserRole.ADMIN,
    }

    if account_type == "individual" and user.role != UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu hesap kurumsal kullanıcı hesabıdır. Kurumsal giriş sekmesini kullanın.",
        )

    if account_type == "institutional" and user.role not in institutional_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu hesap bireysel kullanıcı hesabıdır. Bireysel giriş sekmesini kullanın.",
        )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> TokenResponse:
    """Create a privacy-minimal individual account.

    Public registration always creates a PATIENT/individual account. Doctor,
    laboratory and admin accounts are provisioned through institutional/admin
    workflows rather than self-selected from the public registration screen.
    """

    _validate_password(payload.password)

    async with AsyncSessionFactory() as session:
        existing = (
            await session.execute(select(User).where(User.nickname == payload.nickname))
        ).scalar_one_or_none()

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu rumuz zaten kullanılıyor.",
            )

        user = User(
            nickname=payload.nickname,
            email=None,
            full_name=None,
            role=UserRole.PATIENT,
            hashed_password=get_password_hash(payload.password),
            is_active=True,
            is_superuser=False,
        )
        session.add(user)

        try:
            await session.flush()
            await session.commit()
            await session.refresh(user)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu rumuz zaten kullanılıyor.",
            ) from exc

    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = await _authenticate_user(payload.nickname, payload.password)
    _validate_account_type(user, payload.account_type)
    return _token_response(user)


@router.post("/token", response_model=TokenResponse)
async def token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    # OAuth2 calls the identifier field "username"; MediCore interprets it as nickname.
    user = await _authenticate_user(form_data.username, form_data.password)
    return _token_response(user)


async def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth token missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise JWTError("missing subject")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired auth token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with AsyncSessionFactory() as session:
        user = await session.get(User, uuid.UUID(str(user_id)))

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user.",
        )
    return current_user


def require_roles(*roles: UserRole):
    async def _dependency(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return current_user

    return _dependency


require_doctor = require_roles(UserRole.DOCTOR, UserRole.ADMIN)
