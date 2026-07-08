"""Authentication routes for MediCore AI.

Adds demo-safe account creation plus JWT login.

Endpoints:
- POST /auth/register
- POST /auth/login
- POST /auth/token  (OAuth2 form-compatible)

Notes:
- For MVP/demo, self-registration is enabled.
- For production, doctor/admin registration should require invitation or admin approval.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.domain.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import AsyncSessionFactory

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole = UserRole.DOCTOR


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_email(email: str) -> None:
    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Geçerli bir e-posta adresi gir.",
        )


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
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(subject=str(user.id), role=str(user.role))
    return TokenResponse(access_token=token, user=_user_out(user))


async def _get_user_by_email(email: str) -> User | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


async def _authenticate_user(email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    user = await _get_user_by_email(normalized_email)

    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu kullanıcı pasif durumda.",
        )

    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> TokenResponse:
    email = _normalize_email(payload.email)
    _validate_email(email)
    _validate_password(payload.password)

    safe_roles = {
        UserRole.DOCTOR,
        UserRole.PATIENT,
        UserRole.LAB_STAFF,
    }
    role = payload.role if payload.role in safe_roles else UserRole.DOCTOR

    async with AsyncSessionFactory() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu e-posta ile kayıtlı kullanıcı zaten var.",
            )

        user = User(
            email=email,
            full_name=payload.full_name.strip(),
            role=role,
            hashed_password=get_password_hash(payload.password),
            is_active=True,
            is_superuser=False,
        )
        session.add(user)

        try:
            await session.flush()
            await session.commit()
            await session.refresh(user)
        except Exception:
            await session.rollback()
            raise

    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    user = await _authenticate_user(payload.email, payload.password)
    return _token_response(user)


@router.post("/token", response_model=TokenResponse)
async def token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
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