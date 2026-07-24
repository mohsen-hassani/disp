# M3 — contract.py

**Status:** Complete

**Scope:** `TileSize`, `TileSpec`, `SettingsPanelSpec`, `ScheduledJobSpec`, `NotificationTypeSpec`, `ModuleManifest` (+ domain-prefix cross-field validator), `TileAction`/`TileItem`/`TileData`, `PlatformModule` Protocol, `TileContext`.

Covers TECHNICAL-SPEC.md §8 (The module contract).

---

## §8. The module contract

`src/disp/core/contract.py` MUST define exactly the following. Field names, types, and defaults are normative.

### 8.1 Specification models

```python
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
    schema_model: type[BaseModel]  # the Pydantic model describing the form
    scope: Literal["user", "global"] = "user"


class ScheduledJobSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=KEY_RE)  # unique task name, e.g. "notes.cleanup"
    cron: str  # 5-field cron, validated at registration
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
```

**Cross-field validation** — `ModuleManifest` MUST enforce, via a model validator, that every `key` in `tiles`, `settings_panels`, `scheduled_jobs`, and `notification_types` begins with `f"{domain}."`. Violations raise `ValueError` at import time.

### 8.2 Tile data models

```python
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
```

### 8.3 The module interface

```python
class PlatformModule(Protocol):
    manifest: ModuleManifest

    def register(self, platform: "Platform") -> None: ...
    def api_router(self) -> APIRouter | None: ...
    def tile_provider(self, key: str) -> TileProvider | None: ...
```

`TileProvider` is `Callable[[TileContext], Awaitable[TileData]]`, where:

```python
@dataclass(frozen=True)
class TileContext:
    user: CurrentUser
    session: AsyncSession
    platform: "Platform"
    now: datetime  # timezone-aware, in MYSTUFF_TIMEZONE
```

Every module package MUST expose a module-level function:

```python
def get_module() -> PlatformModule: ...
```

It MUST be idempotent and side-effect free apart from constructing the object.

### 8.4 The `Platform` facade

`src/disp/core/platform.py` MUST define a `Platform` dataclass that is the **only** object passed to `register()`:

```python
@dataclass
class Platform:
    settings: Settings
    events: EventBus
    scheduler: SchedulerFacade  # .task(name), .defer(name, **kwargs)
    notifier: NotifierFacade  # .send(...)
    store: SettingsStore
    registry: "Registry"  # read-only accessors only
```

Modules MUST NOT import `create_app`, the SQLAlchemy engine, or anything from `disp.core.auth` other than the three public names in §10.1.

(Note: `Platform` itself is built at M10, not here — `contract.py` only defines the `TileContext`/`PlatformModule` types that reference it via `TYPE_CHECKING` forward references, since `platform.py` doesn't exist yet at this milestone.)
