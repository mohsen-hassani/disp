from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from fastapi import APIRouter

from disp.core.contract import ModuleManifest, PlatformModule, TileProvider
from disp.core.db import session_scope
from disp.modules.learning import reminders
from disp.modules.learning.events import CourseIndexed, MasteryUpdated, PathItemCompleted
from disp.modules.learning.manifest import MANIFEST
from disp.modules.learning.router import router
from disp.modules.learning.service import ingest as ingest_service
from disp.modules.learning.service import path as path_service
from disp.modules.learning.tiles import learning_next_up_tile

if TYPE_CHECKING:
    from disp.core.platform import Platform

logger = structlog.get_logger(__name__)


def _log_course_indexed(event: CourseIndexed) -> None:
    logger.info(
        "learning_course_indexed",
        course_id=str(event.course_id),
        topic_count=event.topic_count,
        unmatched_count=event.unmatched_count,
    )


def _log_path_item_completed(event: PathItemCompleted) -> None:
    logger.info(
        "learning_path_item_completed",
        course_id=str(event.course_id),
        path_item_id=str(event.path_item_id),
        score=event.score,
    )


def _log_mastery_updated(event: MasteryUpdated) -> None:
    logger.info(
        "learning_mastery_updated",
        course_id=str(event.course_id),
        topic_tag_id=str(event.topic_tag_id),
        old_score=event.old_score,
        new_score=event.new_score,
    )


class LearningModule:
    manifest: ModuleManifest = MANIFEST

    def register(self, platform: "Platform") -> None:
        # §16.2/§16.3: ad-hoc tasks, dispatched by `defer()` from an HTTP
        # route, on their own queue — NOT bound to a cron, so they are
        # deliberately absent from the manifest's `scheduled_jobs` (see
        # manifest.py's comment on why that field doesn't apply to them).
        @platform.scheduler.task("learning.index_course", queue="learning")
        async def _index_course(**kwargs: Any) -> None:
            job_id = UUID(str(kwargs["job_id"]))
            await ingest_service.run_index_job(platform, job_id)

        @platform.scheduler.task("learning.generate_path", queue="learning")
        async def _generate_path(**kwargs: Any) -> None:
            job_id = UUID(str(kwargs["job_id"]))
            await path_service.run_generate_path_job(platform, job_id)

        # Periodic (manifest-declared cron, §7) — the default queue, not
        # "learning": index/path-gen jobs can run for minutes and would
        # otherwise delay a same-day reminder behind them.
        @platform.scheduler.task("learning.daily_nudge")
        async def _daily_nudge(**_kwargs: Any) -> None:
            async with session_scope() as session:
                notified = await reminders.notify_due(session, platform)
            logger.info("learning_daily_nudge_completed", notified=notified)

        platform.events.subscribe(CourseIndexed, _log_course_indexed)
        platform.events.subscribe(PathItemCompleted, _log_path_item_completed)
        platform.events.subscribe(MasteryUpdated, _log_mastery_updated)

    def api_router(self) -> APIRouter | None:
        return router

    def tile_provider(self, key: str) -> TileProvider | None:
        if key == "learning.next_up":
            return learning_next_up_tile
        return None


def get_module() -> PlatformModule:
    return LearningModule()


__all__ = ["get_module"]
