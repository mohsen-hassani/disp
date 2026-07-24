from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1)
    device_label: str | None = Field(default=None, max_length=64)


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    display_name: str
    is_admin: bool


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 scheme name, not a credential
    expires_in: int
    user: UserOut


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    display_name: str
    is_admin: bool
    auth_method: str


class ApiTokenOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class CreateApiTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    expires_in_days: int | None = Field(default=None, ge=1)


class CreateApiTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    token: str


class CreateInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    is_admin: bool = False


class InviteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    is_admin: bool
    expires_at: datetime
    created_at: datetime


class CreateInviteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    token: str
    accept_url: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
