from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserPublic(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    avatar_url: str | None
    is_verified: bool
    credits_balance: int
    storage_bytes_used: int
    preferences: dict
    created_at: datetime
    last_login_at: datetime | None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = None
    preferences: dict | None = None


class SessionPublic(ORMModel):
    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    is_current: bool = False


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["*"])
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyPublic(ORMModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class ApiKeyCreated(ApiKeyPublic):
    key: str  # plaintext, shown exactly once
