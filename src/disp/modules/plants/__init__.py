from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter

from disp.core.contract import ModuleManifest, PlatformModule, TileProvider
from disp.core.db import session_scope
from disp.modules.plants.events import CareCompleted
from disp.modules.plants.manifest import MANIFEST
from disp.modules.plants.reminders import notify_due
from disp.modules.plants.router import router
from disp.modules.plants.tiles import plants_due_tile

if TYPE_CHECKING:
    from disp.core.platform import Platform

logger = structlog.get_logger(__name__)


def _log_care_completed(event: CareCompleted) -> None:
    logger.info(
        "plant_care_completed",
        plant_id=str(event.plant_id),
        interval_id=str(event.interval_id),
        action_name=event.action_name,
        days_late=event.days_late,
    )


class PlantsModule:
    manifest: ModuleManifest = MANIFEST

    def register(self, platform: "Platform") -> None:
        platform.events.subscribe(CareCompleted, _log_care_completed)

        @platform.scheduler.task("plants.daily_check")
        async def _daily_check(**_kwargs: object) -> None:
            # Its own session: this runs in the worker process, where no
            # request-scoped session exists.
            async with session_scope() as session:
                notified = await notify_due(session, platform)
            logger.info("plants_daily_check_completed", notified=notified)

    def api_router(self) -> APIRouter | None:
        return router

    def tile_provider(self, key: str) -> TileProvider | None:
        if key == "plants.due":
            return plants_due_tile
        return None


def get_module() -> PlatformModule:
    return PlantsModule()


__all__ = ["get_module"]
