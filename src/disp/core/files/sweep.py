"""The sweeper — core.sweep_files (M18-files.md §8.3).

Two passes, both bounded by grace_seconds: soft-deleted rows past grace get
their object removed then their row removed (Pass A); storage objects with
no matching row at all, past grace, get removed (Pass B). Pass B never
touches rows, and no pass ever deletes a row because its object is missing
(I3) — that protects the DB-only-restore scenario in §15.3: an object
without a row is garbage, but a row without an object is an alert.

Cron binding deliberately does NOT follow core.daily_planner's pattern
(scheduler.py's `@app.periodic(cron=get_settings()...)`, evaluated at import
time). Task *registration* here is static; the cron *binding* happens later,
explicitly, against a live Settings instance, via
`scheduler.register_periodic(...)` — the same mechanism Registry.wire()
already uses for every module-owned job. See app.py/worker.py.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.db import session_scope
from disp.core.files.store import FileStore, StorageBackend
from disp.core.models import Asset
from disp.core.scheduler import SchedulerFacade

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SweepResult:
    swept_rows: int
    swept_objects: int
    skipped_in_grace: int


async def run_sweep(
    session: AsyncSession,
    *,
    backend: StorageBackend,
    grace_seconds: int,
    now: datetime,
) -> SweepResult:
    cutoff = now - timedelta(seconds=grace_seconds)

    # Pass A: soft-deleted rows past grace.
    expired_result = await session.execute(
        select(Asset).where(Asset.deleted_at.is_not(None), Asset.deleted_at < cutoff)
    )
    swept_rows = 0
    for asset in expired_result.scalars():
        await backend.delete(asset.storage_key)
        await session.delete(asset)
        swept_rows += 1

    skipped_result = await session.execute(
        select(Asset.id).where(Asset.deleted_at.is_not(None), Asset.deleted_at >= cutoff)
    )
    skipped_in_grace = len(skipped_result.scalars().all())

    # Pass B: storage objects with no matching row at all (any row, deleted
    # or not — a soft-deleted-but-not-yet-swept row's object is Pass A's
    # concern, not an orphan), past grace so an in-flight put() mid-write
    # never gets raced.
    known_keys_result = await session.execute(select(Asset.storage_key))
    known_keys = set(known_keys_result.scalars().all())

    swept_objects = 0
    async for key, last_modified in backend.iter_objects():
        if key in known_keys or last_modified >= cutoff:
            continue
        await backend.delete(key)
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
    """Registers the core.sweep_files task. Idempotent — unlike
    core.daily_planner (registered once at scheduler.py's import time via a
    module-level decorator), this runs inside create_app()/_build_platform(),
    which a single process can call more than once (e.g.
    tests/core/test_plugin_proof.py builds a second, module-restricted app in
    the same process). Returns whether this call freshly registered the task
    — callers should only bind the cron (register_periodic) when it did, since
    Procrastinate's periodic registry isn't idempotent either.

    Cron binding itself is a separate, later call to
    scheduler.register_periodic — see module docstring. `session_maker` is
    normally left unset (session_scope() then builds the shared background
    one); tests pass one so the task body can be exercised directly against
    a per-test transaction rather than a real commit."""
    if scheduler.has_task("core.sweep_files"):
        return False

    @scheduler.task(name="core.sweep_files", queue="default", retry=3)
    async def sweep_files(timestamp: int) -> None:
        from disp.core.config import get_settings

        settings = get_settings()
        files = FileStore.from_settings(settings)
        now = datetime.fromtimestamp(timestamp, tz=UTC)
        async with session_scope(session_maker) as session:
            await run_sweep(
                session,
                backend=files.backend,
                grace_seconds=settings.files_sweep_grace_seconds,
                now=now,
            )

    return True
