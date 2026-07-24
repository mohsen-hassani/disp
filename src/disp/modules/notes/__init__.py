from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter

from disp.core.contract import ModuleManifest, PlatformModule, TileProvider
from disp.core.db import session_scope
from disp.modules.notes import service
from disp.modules.notes.events import NoteCreated
from disp.modules.notes.manifest import MANIFEST
from disp.modules.notes.router import router
from disp.modules.notes.tiles import notes_latest_tile

if TYPE_CHECKING:
    from disp.core.platform import Platform

logger = structlog.get_logger(__name__)


def _log_note_created(event: NoteCreated) -> None:
    logger.info("note_created", note_id=str(event.note_id), user_id=str(event.user_id))


class NotesModule:
    manifest: ModuleManifest = MANIFEST

    def register(self, platform: "Platform") -> None:
        platform.events.subscribe(NoteCreated, _log_note_created)

        @platform.scheduler.task("notes.purge_deleted")
        async def _purge_deleted(**_kwargs: object) -> None:
            async with session_scope() as session:
                count = await service.purge_deleted(session)
            logger.info("notes_purge_deleted_completed", count=count)

    def api_router(self) -> APIRouter | None:
        return router

    def tile_provider(self, key: str) -> TileProvider | None:
        if key == "notes.latest":
            return notes_latest_tile
        return None


def get_module() -> PlatformModule:
    return NotesModule()


__all__ = ["get_module"]
