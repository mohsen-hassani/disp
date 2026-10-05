"""Delete → purge after commit (M18-files.md §8.2, I2).

`files` is built on the per-test `session_maker`, so the purge's own fresh
session joins the test transaction and can see the test's committed (i.e.
SAVEPOINT-released) marks — exactly the visibility a real deployment has
after a real commit.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from disp.core.config import Settings
from disp.core.db import create_session_maker
from disp.core.files.store import ACCEPT_IMAGES, FileStore
from disp.core.models import FileRecord
from tests.core.files.conftest import PNG_1PX, SpyBackend, bucket_keys
from tests.factories import make_user


async def _stored_key(files: FileStore, session: AsyncSession, owner: UUID) -> tuple[UUID, str]:
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
    return stored.id, record.storage_key


async def test_delete_then_commit_purges_object_and_row(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="purge-commit@example.com")
    file_id, key = await _stored_key(files, db_session, user.id)
    await db_session.commit()
    assert key in await bucket_keys(files)

    await files.delete(db_session, file_id, domain="plants")
    # Nothing leaves the bucket before the commit (I2).
    assert key in await bucket_keys(files)
    await db_session.commit()
    await files.wait_for_purges()

    assert key not in await bucket_keys(files)
    db_session.expunge_all()
    assert await db_session.get(FileRecord, file_id) is None


async def test_delete_then_rollback_purges_nothing(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="purge-rollback@example.com")
    file_id, key = await _stored_key(files, db_session, user.id)
    await db_session.commit()

    await files.delete(db_session, file_id, domain="plants")
    await db_session.rollback()
    await files.wait_for_purges()
    # A later, unrelated commit must not resurrect the discarded purge.
    await db_session.commit()
    await files.wait_for_purges()

    assert key in await bucket_keys(files)
    record = await db_session.get(FileRecord, file_id)
    assert record is not None and record.deleted_at is None


async def test_purge_ignores_marks_it_cannot_see_as_committed(
    files_settings: Settings,
    engine: AsyncEngine,
    db_session: AsyncSession,
) -> None:
    """The purge only acts on marks visible from a fresh session on its own
    connection, i.e. committed ones. This is what makes the post-commit hook
    a safe no-op in route tests, whose "commit" only releases a SAVEPOINT
    inside a transaction no other connection can see."""
    spy = SpyBackend()
    files = FileStore(
        {"s3": spy},
        active="s3",
        settings=files_settings,
        session_maker=create_session_maker(engine),  # a separate connection
    )
    user = await make_user(db_session, email="purge-uncommitted@example.com")
    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=PNG_1PX,
        accept=ACCEPT_IMAGES,
    )
    await files.delete(db_session, stored.id, domain="plants")
    await db_session.flush()  # the mark is in the test transaction, uncommitted

    assert await files.purge([stored.id]) == 0
    assert await files.purge() == 0
    assert spy.deletes == []


async def test_a_failed_object_delete_leaves_the_mark_for_the_sweeper(
    files_settings: Settings,
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    spy = SpyBackend(fail_delete=True)
    files = FileStore(
        {"s3": spy}, active="s3", settings=files_settings, session_maker=session_maker
    )
    user = await make_user(db_session, email="purge-fail@example.com")
    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=PNG_1PX,
        accept=ACCEPT_IMAGES,
    )
    await db_session.commit()

    await files.delete(db_session, stored.id, domain="plants")
    await db_session.commit()
    await files.wait_for_purges()

    db_session.expunge_all()
    record = await db_session.get(FileRecord, stored.id)
    assert record is not None and record.deleted_at is not None

    # Once storage recovers, the next purge (the sweeper's pass A) finishes it.
    spy.fail_delete = False
    assert await files.purge() == 1
    db_session.expunge_all()
    assert await db_session.get(FileRecord, stored.id) is None
    assert spy.deletes == [(spy.bucket, record.storage_key)]


async def test_purge_is_idempotent_against_a_row_already_gone(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="purge-twice@example.com")
    file_id, _ = await _stored_key(files, db_session, user.id)
    await files.delete(db_session, file_id, domain="plants")
    await db_session.commit()
    await files.wait_for_purges()

    assert await files.purge([file_id]) == 0
