from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    nickname: str = Field(min_length=3, max_length=32)
    password: str
    account_type: Literal["individual", "institutional"] = "individual"


class AuthUserResponse(BaseModel):
    id: str
    nickname: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
