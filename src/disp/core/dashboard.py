import asyncio
from datetime import datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from disp import __version__
from disp.core.auth import CurrentUser, current_user
from disp.core.config import get_settings
from disp.core.contract import (
    ClientNavSpec,
    NotificationTypeSpec,
    SettingsPanelSpec,
    TileContext,
    TileData,
    TileSpec,
)
from disp.core.db import get_session
from disp.core.errors import AppError
from disp.core.platform import Platform
from disp.core.registry import Registry

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["dashboard"])

TILE_RENDER_TIMEOUT_SECONDS = 3


class SettingsPanelOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    description: str | None
    scope: Literal["user", "global"]
    # JSON Schema (WEB-SPEC §3 amendment A1), produced from schema_model.model_json_schema()
    # so a JS client can render a settings form without a Pydantic-aware codegen step.
    # mode="serialization" (not the default "validation") per the amendment's literal text —
    # a field with a custom serializer could otherwise disagree with what the client receives.
    # Aliased to "schema" on the wire; the attribute itself can't be named `schema` without
    # shadowing pydantic.BaseModel's own deprecated `.schema()` method.
    schema_: dict[str, Any] = Field(alias="schema")


class ModuleManifestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    name: str
    version: str
    description: str | None
    tiles: list[TileSpec]
    settings_panels: list[SettingsPanelOut]
    notification_types: list[NotificationTypeSpec]
    # None for a module with no client screens -- it renders on the dashboard
    # but never in navigation. Reused as-is from the contract, like TileSpec
    # below, so a field added there reaches the client with no mapping code.
    client_nav: ClientNavSpec | None = None


class DashboardManifestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform_version: str
    modules: list[ModuleManifestOut]


class TilesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tiles: list[TileData]


def _fallback_tile(spec: TileSpec, now: datetime) -> TileData:
    return TileData(
        key=spec.key,
        title=spec.title,
        count=None,
        items=[],
        actions=[],
        empty_text="This tile failed to load",
        generated_at=now,
    )


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def _serialize_panel(panel: SettingsPanelSpec) -> SettingsPanelOut:
    return SettingsPanelOut(
        key=panel.key,
        title=panel.title,
        description=panel.description,
        scope=panel.scope,
        schema=panel.schema_model.model_json_schema(mode="serialization"),
    )


@router.get(
    "/manifest",
    response_model=DashboardManifestResponse,
    status_code=200,
    summary="Get the platform's full capability index",
    operation_id="dashboard_manifest",
)
async def get_manifest(
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
) -> DashboardManifestResponse:
    registry: Registry = request.app.state.registry
    modules: list[ModuleManifestOut] = []
    seen_panel_keys: set[str] = set()
    for dm in registry.modules:
        modules.append(
            ModuleManifestOut(
                domain=dm.manifest.domain,
                name=dm.manifest.name,
                version=dm.manifest.version,
                description=dm.manifest.description,
                tiles=list(dm.manifest.tiles),
                settings_panels=[_serialize_panel(panel) for panel in dm.manifest.settings_panels],
                notification_types=list(dm.manifest.notification_types),
                client_nav=dm.manifest.client_nav,
            )
        )
        seen_panel_keys.update(panel.key for panel in dm.manifest.settings_panels)

    # Settings panels registered directly on the core platform (via
    # Registry.register_core_settings_panel, e.g. core.notifier) belong to no
    # discovered module (disp.modules/* discovery never sees `core`), so the
    # loop above never surfaces them. Without this, the manifest silently
    # omits every core-owned panel even though GET/PUT /api/settings/{domain}
    # already serves them. Surface the remainder under a synthetic "core"
    # entry so the client's /settings index has something to list at all.
    core_only_panels = [
        panel for key, panel in registry.settings_panels.items() if key not in seen_panel_keys
    ]
    if core_only_panels:
        modules.append(
            ModuleManifestOut(
                domain="core",
                name="Core",
                version=__version__,
                description="Built-in platform settings.",
                tiles=[],
                settings_panels=[_serialize_panel(panel) for panel in core_only_panels],
                notification_types=[],
            )
        )

    return DashboardManifestResponse(platform_version=__version__, modules=modules)


async def _render_tile(
    request: Request,
    session: AsyncSession,
    user: CurrentUser,
    spec: TileSpec,
    now: datetime,
) -> TileData:
    registry: Registry = request.app.state.registry
    platform: Platform = request.app.state.platform
    provider = registry.tile_provider_for(spec.key)
    if provider is None:
        return _fallback_tile(spec, now)

    ctx = TileContext(user=user, session=session, platform=platform, now=now)
    try:
        async with asyncio.timeout(TILE_RENDER_TIMEOUT_SECONDS):
            return await provider(ctx)
    except Exception as exc:  # a failing/timed-out provider must not fail the whole response
        logger.error("tile_render_failed", tile_key=spec.key, exc_info=exc)
        return _fallback_tile(spec, now)


@router.get(
    "/tiles",
    response_model=TilesResponse,
    status_code=200,
    summary="Render every registered tile for the caller",
    operation_id="dashboard_tiles",
)
async def get_tiles(
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TilesResponse:
    registry: Registry = request.app.state.registry
    now = _now_local()
    specs = sorted(registry.tiles.values(), key=lambda spec: (spec.order, spec.key))
    tiles = [await _render_tile(request, session, user, spec, now) for spec in specs]
    return TilesResponse(tiles=tiles)


@router.get(
    "/tiles/{tile_key}",
    response_model=TileData,
    status_code=200,
    summary="Render a single tile",
    operation_id="dashboard_tile",
    responses={404: {"description": "Unknown tile key"}},
)
async def get_tile(
    tile_key: str,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TileData:
    registry: Registry = request.app.state.registry
    spec = registry.tiles.get(tile_key)
    provider = registry.tile_provider_for(tile_key)
    if spec is None or provider is None:
        raise AppError(
            status_code=404,
            code="dashboard.tile_not_found",
            title="Tile not found",
            detail=f"No tile is registered under key {tile_key!r}.",
        )

    platform: Platform = request.app.state.platform
    ctx = TileContext(user=user, session=session, platform=platform, now=_now_local())
    return await provider(ctx)
