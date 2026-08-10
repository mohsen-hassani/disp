"""The sweeper — core.sweep_files (M18-files.md §8.3, §15.3)."""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import procrastinate
import pytest
from procrastinate import testing as procrastinate_testing
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import get_settings
from disp.core.files.backends.local import LocalBackend
from disp.core.files.sweep import register_task, run_sweep
from disp.core.models import Asset
from disp.core.scheduler import SchedulerFacade
from tests.factories import make_user

GRACE = 86400


async def _make_asset(
    session: AsyncSession,
    backend: LocalBackend,
    *,
    owner_id: uuid.UUID,
    key: str,
    deleted_at: datetime | None = None,
) -> Asset:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"x"

    await backend.write(key, chunks())
    asset = Asset(
        owner_user_id=owner_id,
        domain="plants",
        purpose="plant_photo",
        content_type="image/png",
        byte_size=1,
        sha256="0" * 64,
        backend="local",
        storage_key=key,
        deleted_at=deleted_at,
    )
    session.add(asset)
    await session.flush()
    return asset


async def test_pass_a_sweeps_soft_deleted_rows_past_grace(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    backend = LocalBackend(tmp_path)
    user = await make_user(db_session, email="sweep-a@example.com")
    now = datetime.now(UTC)

    expired = await _make_asset(
        db_session,
        backend,
        owner_id=user.id,
        key="a/expired.bin",
        deleted_at=now - timedelta(seconds=GRACE + 3600),
    )
    fresh = await _make_asset(
        db_session,
        backend,
        owner_id=user.id,
        key="a/fresh.bin",
        deleted_at=now - timedelta(seconds=60),
    )

    result = await run_sweep(db_session, backend=backend, grace_seconds=GRACE, now=now)

    assert result.swept_rows == 1
    assert result.skipped_in_grace == 1
    assert not await backend.exists("a/expired.bin")
    assert await backend.exists("a/fresh.bin")

    remaining_ids = set((await db_session.execute(select(Asset.id))).scalars().all())
    assert expired.id not in remaining_ids
    assert fresh.id in remaining_ids


async def test_pass_b_sweeps_orphaned_objects_past_grace(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    backend = LocalBackend(tmp_path)
    now = datetime.now(UTC)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"x"

    await backend.write("orphan/old.bin", chunks())
    await backend.write("orphan/new.bin", chunks())

    old_path = tmp_path / "orphan" / "old.bin"
    old_mtime = (now - timedelta(seconds=GRACE + 3600)).timestamp()
    os.utime(old_path, (old_mtime, old_mtime))

    result = await run_sweep(db_session, backend=backend, grace_seconds=GRACE, now=now)

    assert result.swept_objects == 1
    assert not await backend.exists("orphan/old.bin")
    # Within grace — protects an in-flight put() whose transaction hasn't
    # committed yet from being raced by the sweeper.
    assert await backend.exists("orphan/new.bin")


async def test_row_with_missing_object_survives_a_sweep(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    """I3: the sweeper never deletes a row because its object is missing —
    this is what protects the DB-only-restore scenario (§15.3): an object
    without a row is garbage, but a row without an object is an alert."""
    backend = LocalBackend(tmp_path)
    user = await make_user(db_session, email="sweep-i3@example.com")
    now = datetime.now(UTC)

    asset = Asset(
        owner_user_id=user.id,
        domain="plants",
        purpose="plant_photo",
        content_type="image/png",
        byte_size=1,
        sha256="0" * 64,
        backend="local",
        storage_key="never/written.bin",
    )
    db_session.add(asset)
    await db_session.flush()

    result = await run_sweep(db_session, backend=backend, grace_seconds=GRACE, now=now)

    assert result.swept_rows == 0
    row = (await db_session.execute(select(Asset).where(Asset.id == asset.id))).scalar_one_or_none()
    assert row is not None


async def test_sweep_is_safe_to_run_concurrently_with_itself(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    backend = LocalBackend(tmp_path)
    user = await make_user(db_session, email="sweep-concurrent@example.com")
    now = datetime.now(UTC)

    await _make_asset(
        db_session,
        backend,
        owner_id=user.id,
        key="a/expired.bin",
        deleted_at=now - timedelta(seconds=GRACE + 3600),
    )

    first = await run_sweep(db_session, backend=backend, grace_seconds=GRACE, now=now)
    second = await run_sweep(db_session, backend=backend, grace_seconds=GRACE, now=now)

    assert first.swept_rows == 1
    assert second.swept_rows == 0
    assert second.swept_objects == 0


async def test_register_task_wires_a_working_sweep_files_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """Exercises the actual scheduled-task body (register_task's inner
    closure), not just run_sweep directly — a throwaway procrastinate.App
    sidesteps both the process-wide scheduler singleton (already carrying a
    real core.sweep_files registration from other tests' `app` fixture) and
    register_task's own idempotency guard, which would otherwise make a
    second registration on the shared App a silent no-op."""
    monkeypatch.setenv("DISP_FILES_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        test_app = procrastinate.App(connector=procrastinate_testing.InMemoryConnector())
        scheduler = SchedulerFacade(test_app)
        register_task(scheduler, session_maker=session_maker)
        task = test_app.tasks["core.sweep_files"]

        user = await make_user(db_session, email="sweep-task-body@example.com")
        backend = LocalBackend(tmp_path)
        now = datetime.now(UTC)
        await _make_asset(
            db_session,
            backend,
            owner_id=user.id,
            key="a/expired.bin",
            deleted_at=now - timedelta(seconds=GRACE + 3600),
        )

        await task.func(int((now + timedelta(seconds=GRACE + 3600)).timestamp()))

        remaining = (await db_session.execute(select(Asset.storage_key))).scalars().all()
        assert "a/expired.bin" not in remaining
    finally:
        get_settings.cache_clear()
