from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from disp.core.auth import CurrentUser
    from disp.core.platform import Platform

DOMAIN_RE = r"^[a-z][a-z0-9_]{1,31}$"
KEY_RE = r"^[a-z][a-z0-9_]{1,31}\.[a-z][a-z0-9_]{1,63}$"  # "<domain>.<name>"


class TileSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class TileSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=KEY_RE)
    title: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    size: TileSize = TileSize.MEDIUM
    refresh_seconds: int = Field(default=300, ge=10, le=86400)
    order: int = Field(default=100, ge=0, le=1000)


class SettingsPanelSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=KEY_RE)
    title: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    schema_model: type[BaseModel]
    scope: Literal["user", "global"] = "user"


class ScheduledJobSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=KEY_RE)  # unique task name, e.g. "notes.cleanup"
    cron: str
    description: str | None = None


class NotificationTypeSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(pattern=KEY_RE)
    title: str = Field(min_length=1, max_length=80)
    description: str | None = None
    default_enabled: bool = True


class ModuleManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: str = Field(pattern=DOMAIN_RE)
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str | None = Field(default=None, max_length=300)
    dependencies: tuple[str, ...] = ()
    tiles: tuple[TileSpec, ...] = ()
    settings_panels: tuple[SettingsPanelSpec, ...] = ()
    scheduled_jobs: tuple[ScheduledJobSpec, ...] = ()
    notification_types: tuple[NotificationTypeSpec, ...] = ()

    @model_validator(mode="after")
    def _validate_key_prefixes(self) -> "ModuleManifest":
        prefix = f"{self.domain}."
        for tile in self.tiles:
            if not tile.key.startswith(prefix):
                raise ValueError(f"tile key {tile.key!r} must start with {prefix!r}")
        for panel in self.settings_panels:
            if not panel.key.startswith(prefix):
                raise ValueError(f"settings panel key {panel.key!r} must start with {prefix!r}")
        for job in self.scheduled_jobs:
            if not job.name.startswith(prefix):
                raise ValueError(f"scheduled job name {job.name!r} must start with {prefix!r}")
        for notification_type in self.notification_types:
            if not notification_type.key.startswith(prefix):
                raise ValueError(
                    f"notification type key {notification_type.key!r} must start with {prefix!r}"
                )
        return self


class TileAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str  # "quick_add"
    label: str
    method: Literal["POST", "PATCH", "DELETE"]
    path: str  # "/api/notes"
    body_schema: dict[str, Any] | None = None  # JSON Schema, or None


class TileItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    primary: str  # main line of text
    secondary: str | None = None
    timestamp: datetime | None = None
    done: bool | None = None  # renders a checkbox when not None
    href: str | None = None  # deep link into the module's API


class TileData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    count: int | None = None  # headline number, if meaningful
    items: list[TileItem] = []
    actions: list[TileAction] = []
    empty_text: str = "Nothing here"
    generated_at: datetime


@dataclass(frozen=True)
class TileContext:
    user: "CurrentUser"
    session: AsyncSession
    platform: "Platform"
    now: datetime  # timezone-aware, in DISP_TIMEZONE


TileProvider = Callable[[TileContext], Awaitable[TileData]]


class PlatformModule(Protocol):
    manifest: ModuleManifest

    def register(self, platform: "Platform") -> None: ...
    def api_router(self) -> APIRouter | None: ...
    def tile_provider(self, key: str) -> TileProvider | None: ...
