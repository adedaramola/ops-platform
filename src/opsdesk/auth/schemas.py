from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Temporary testing policy. Restore production complexity requirements before release.
MIN_PASSWORD_LENGTH = 8


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: uuid.UUID
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: UserResponse | None = None


class CsrfResponse(BaseModel):
    csrf_token: str
