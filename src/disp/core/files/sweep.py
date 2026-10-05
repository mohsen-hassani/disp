"""The sweeper — core.sweep_files (M18-files.md §8.3).

The safety net under the post-commit purge, so that nothing stale outlives
one sweep interval in a bucket that bills per GB (I7):

- Pass A: every row marked deleted → object, then row (FileStore.purge).
  Catches purges that failed or never ran (process died between commit and
  task).
- Pass B: every object under the prefix with no row at all, older than the
  orphan grace → delete. Catches rolled-back uploads and user-delete
  cascades. The grace stops it racing an in-flight put() whose transaction
  hasn't committed yet.

No pass ever deletes a row because its object is missing (I3): an object
without a row is garbage, a row without an object is an alert
(`disp-admin files verify`).

Cron binding is explicit and late — `scheduler.register_periodic(...)`
against a live Settings in app.py/worker.py — not core.daily_planner's
import-time `@app.periodic` decorator.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.files.store import FileStore
from disp.core.models import FileRecord
from disp.core.scheduler import SchedulerFacade

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SweepResult:
    swept_rows: int
    swept_objects: int
    skipped_in_grace: int


async def run_sweep(files: FileStore, *, grace_seconds: int, now: datetime) -> SweepResult:
    swept_rows = await files.purge()

    backend = files.backend
    async with files.open_session() as session:
        # Every row of any status counts as "known": a marked-but-unpurged
        # row's object is pass A's concern, never an orphan.
        result = await session.execute(
            select(FileRecord.storage_key).where(
                FileRecord.backend == backend.name, FileRecord.bucket == backend.bucket
            )
        )
        known_keys = set(result.scalars().all())

    cutoff = now - timedelta(seconds=grace_seconds)
    swept_objects = 0
    skipped_in_grace = 0
    async for key, last_modified in backend.iter_objects(files.prefix):
        if key in known_keys:
            continue
        if last_modified >= cutoff:
            skipped_in_grace += 1
            continue
        await backend.delete(backend.bucket, key)
        swept_objects += 1

    logger.info(
        "sweep_files_completed",
        swept_rows=swept_rows,
        swept_objects=swept_objects,
        skipped_in_grace=skipped_in_grace,
    )
    return SweepResult(
        swept_rows=swept_rows, swept_objects=swept_objects, skipped_in_grace=skipped_in_grace
    )


def register_task(
    scheduler: SchedulerFacade,
    *,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> bool:
    """Registers the core.sweep_files task. Idempotent — create_app() can run
    more than once per process (tests/core/test_plugin_proof.py builds a
    second app), and Procrastinate's task registry isn't. Returns whether
    this call freshly registered the task; callers bind the cron
    (register_periodic) only when it did. `session_maker` is normally unset
    (the shared background one); tests pass a per-test one."""
    if scheduler.has_task("core.sweep_files"):
        return False

    @scheduler.task(name="core.sweep_files", queue="default", retry=3)
    async def sweep_files(timestamp: int) -> None:
        from disp.core.config import get_settings

        settings = get_settings()
        files = FileStore.from_settings(settings, session_maker=session_maker)
        await run_sweep(
            files,
            grace_seconds=settings.files_orphan_grace_seconds,
            now=datetime.fromtimestamp(timestamp, tz=UTC),
        )

    return True
