"""The sweeper — core.sweep_files (M18-files.md §8.3, I3, I7)."""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

import procrastinate
import pytest
from procrastinate import testing as procrastinate_testing
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import get_settings
from disp.core.files.store import ACCEPT_IMAGES, FileStore
from disp.core.files.sweep import register_task, run_sweep
from disp.core.models import FileRecord
from disp.core.scheduler import SchedulerFacade
from tests.core.files.conftest import PNG_1PX, bucket_keys
from tests.factories import make_user

GRACE = 3600


async def _put(files: FileStore, session: AsyncSession, owner: UUID) -> FileRecord:
    stored = await files.put(
        session,
        owner=owner,
        domain="plants",
        purpose="plant_photo",
        source=PNG_1PX,
        accept=ACCEPT_IMAGES,
    )
    record = await session.get(FileRecord, stored.id)
    assert record is not None
    return record


async def _orphan(files: FileStore, name: str) -> str:
    key = f"{files.prefix}orphans/{name}"
    await files.backend.put(key, BytesIO(b"x"), size=1, content_type="image/png")
    return key


async def test_pass_a_purges_every_marked_row(files: FileStore, db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="sweep-a@example.com")
    marked = await _put(files, db_session, user.id)
    marked.deleted_at = datetime.now(UTC)  # a purge that never ran
    live = await _put(files, db_session, user.id)
    await db_session.commit()

    result = await run_sweep(files, grace_seconds=GRACE, now=datetime.now(UTC))

    assert result.swept_rows == 1
    keys = await bucket_keys(files)
    assert marked.storage_key not in keys
    assert live.storage_key in keys
    db_session.expunge_all()
    assert await db_session.get(FileRecord, marked.id) is None
    assert await db_session.get(FileRecord, live.id) is not None


async def test_pass_b_deletes_old_orphans_and_spares_young_ones(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="sweep-b@example.com")
    referenced = await _put(files, db_session, user.id)
    await db_session.commit()
    orphan = await _orphan(files, "rolled-back.png")

    # Inside the grace window an orphan may be an in-flight put() whose
    # transaction hasn't committed yet: it must survive.
    young = await run_sweep(files, grace_seconds=GRACE, now=datetime.now(UTC))
    assert young.swept_objects == 0
    assert young.skipped_in_grace == 1
    assert orphan in await bucket_keys(files)

    old = await run_sweep(
        files, grace_seconds=GRACE, now=datetime.now(UTC) + timedelta(seconds=GRACE + 60)
    )
    assert old.swept_objects == 1
    keys = await bucket_keys(files)
    assert orphan not in keys
    assert referenced.storage_key in keys


async def test_pass_b_never_reaches_outside_its_prefix(
    files: FileStore, db_session: AsyncSession
) -> None:
    other_prefix_key = f"elsewhere-{uuid4().hex}/keep.png"
    await files.backend.put(other_prefix_key, BytesIO(b"x"), size=1, content_type="image/png")
    try:
        await run_sweep(files, grace_seconds=GRACE, now=datetime.now(UTC) + timedelta(days=30))
        all_keys = {key async for key, _ in files.backend.iter_objects("elsewhere-")}
        assert other_prefix_key in all_keys
    finally:
        await files.backend.delete(files.backend.bucket, other_prefix_key)


async def test_a_row_whose_object_is_missing_survives_every_pass(
    files: FileStore, db_session: AsyncSession
) -> None:
    """I3: a row without an object is an alert, never garbage — e.g. after a
    database restore that predates a purge."""
    user = await make_user(db_session, email="sweep-i3@example.com")
    record = await _put(files, db_session, user.id)
    await db_session.commit()
    await files.backend.delete(record.bucket, record.storage_key)

    await run_sweep(files, grace_seconds=GRACE, now=datetime.now(UTC) + timedelta(days=30))

    db_session.expunge_all()
    survivor = await db_session.get(FileRecord, record.id)
    assert survivor is not None and survivor.deleted_at is None


async def test_sweep_is_safe_to_run_twice(files: FileStore, db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="sweep-twice@example.com")
    marked = await _put(files, db_session, user.id)
    marked.deleted_at = datetime.now(UTC)
    await db_session.commit()

    first = await run_sweep(files, grace_seconds=GRACE, now=datetime.now(UTC))
    second = await run_sweep(files, grace_seconds=GRACE, now=datetime.now(UTC))
    assert (first.swept_rows, second.swept_rows) == (1, 0)
    assert second.swept_objects == 0


async def test_register_task_wires_a_working_sweep_files_task(
    monkeypatch: pytest.MonkeyPatch,
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    """Exercises the scheduled-task body itself. A throwaway procrastinate.App
    sidesteps the process-wide scheduler singleton (already carrying a real
    core.sweep_files from the `app` fixture) and register_task's own
    idempotency guard. The task reads get_settings(), so it gets a private
    prefix here — pass B must not see other tests' objects."""
    prefix = f"t-{uuid4().hex}/"
    monkeypatch.setenv("DISP_FILES_S3_PREFIX", prefix)
    get_settings.cache_clear()
    try:
        test_app = procrastinate.App(connector=procrastinate_testing.InMemoryConnector())
        scheduler = SchedulerFacade(test_app)
        assert register_task(scheduler, session_maker=session_maker) is True
        assert register_task(scheduler, session_maker=session_maker) is False
        task = test_app.tasks["core.sweep_files"]

        files = FileStore.from_settings(get_settings(), session_maker=session_maker)
        user = await make_user(db_session, email="sweep-task@example.com")
        marked = await _put(files, db_session, user.id)
        marked.deleted_at = datetime.now(UTC)
        await db_session.commit()
        orphan = await _orphan(files, "task.png")

        await task.func(int((datetime.now(UTC) + timedelta(days=1)).timestamp()))

        keys = await bucket_keys(files)
        assert marked.storage_key not in keys
        assert orphan not in keys
    finally:
        get_settings.cache_clear()
