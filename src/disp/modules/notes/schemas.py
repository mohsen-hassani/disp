from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    pinned: bool = False


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    pinned: bool | None = None


class NoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str | None
    body: str
    pinned: bool
    created_at: datetime
    updated_at: datetime


class ShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)
    permission: Literal["read", "write"]
