from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """POST /auth/register body."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """POST /auth/login body."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """JWT bearer token returned by /auth/login."""

    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """Public-facing User representation. Never exposes password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    is_active: bool
    created_at: datetime


class RegisterResponse(UserOut):
    """201 response from /auth/register — same shape as UserOut."""


__all__ = [
    "RegisterRequest",
    "LoginRequest",
    "TokenResponse",
    "UserOut",
    "RegisterResponse",
]
