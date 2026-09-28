"""Auth and user schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str
    email: EmailStr
    role: str
    institution_id: str
    institution_code: str
    is_active: bool
    must_change_password: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: WhoAmISchema


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: WhoAmISchema


class ActivateAccountRequest(BaseModel):
    token: str
    full_name: str = Field(min_length=3, max_length=150)
    new_password: str = Field(min_length=10, max_length=128)
    student_self_fields: dict[str, object] | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


class Message(BaseModel):
    message: str


class ReadyToken(BaseModel):
    ready: bool = True


class LoginHistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class WhoAmISchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: str
    institution_id: str
    institution_code: str
    is_active: bool
    must_change_password: bool