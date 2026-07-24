from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core import events as events_module
from disp.core.errors import AppError
from disp.core.events import EventBus, set_event_bus
from disp.modules.notes.models import Note
from disp.modules.notes.schemas import NoteCreate, NoteUpdate
from disp.modules.notes.service import (
    create_note,
    get_note,
    list_notes,
    purge_deleted,
    share_note,
    update_note,
)
from tests.factories import current_user_for, make_user


@pytest.fixture(autouse=True)
def _fresh_event_bus() -> None:
    """Swap in a fresh EventBus for the duration of the test, then restore
    whatever was active before (e.g. the session-scoped `app` fixture's real
    bus) rather than clobbering it for tests that run afterward."""
    previous = events_module._active_bus
    set_event_bus(EventBus())
    yield
    events_module._active_bus = previous


# Case 45: create returns 201 (service-level: persists, OWNER ACL row,
# NoteCreated emitted and the handler ran).


async def test_create_note_persists_grants_owner_and_emits_event(db_session: AsyncSession) -> None:
    from disp.core.auth.acl import can
    from disp.modules.notes.events import NoteCreated

    received: list[NoteCreated] = []

    async def _handler(event: NoteCreated) -> None:
        received.append(event)

    bus = EventBus()
    bus.subscribe(NoteCreated, _handler)
    set_event_bus(bus)

    user = await make_user(db_session, email="notes-create@example.com")
    cu = current_user_for(user)

    note = await create_note(db_session, cu, NoteCreate(body="hello world"))
    await db_session.commit()  # publish_after_commit fires on the sync session's after_commit event

    row = (await db_session.execute(select(Note).where(Note.id == note.id))).scalar_one()
    assert row.body == "hello world"

    assert await can(db_session, cu, "read", "notes.note", str(note.id)) is True
    assert await can(db_session, cu, "share", "notes.note", str(note.id)) is True

    for task in list(events_module._background_tasks):
        await task
    assert [e.note_id for e in received] == [note.id]


# Case 46: list excludes soft-deleted notes and another user's notes.


async def test_list_excludes_deleted_and_other_users_notes(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="notes-list-owner@example.com")
    other = await make_user(db_session, email="notes-list-other@example.com")
    owner_cu = current_user_for(owner)

    visible = await create_note(db_session, owner_cu, NoteCreate(body="visible"))
    to_delete = await create_note(db_session, owner_cu, NoteCreate(body="to delete"))
    await create_note(db_session, current_user_for(other), NoteCreate(body="not mine"))

    note_row = (await db_session.execute(select(Note).where(Note.id == to_delete.id))).scalar_one()
    note_row.deleted_at = datetime.now(UTC)
    await db_session.flush()

    page = await list_notes(db_session, owner_cu, limit=20, cursor=None, q=None, pinned=None)

    ids = {item.id for item in page.items}
    assert ids == {visible.id}


# Case 47: reading another user's note returns 404.


async def test_reading_another_users_note_returns_404(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="notes-404-owner@example.com")
    stranger = await make_user(db_session, email="notes-404-stranger@example.com")

    note = await create_note(db_session, current_user_for(owner), NoteCreate(body="private"))

    with pytest.raises(AppError) as exc_info:
        await get_note(db_session, current_user_for(stranger), note.id)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "notes.not_found"


# Case 48: share with 'read' lets the grantee read but not update (update
# returns 403).


async def test_share_read_permits_read_forbids_write(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="notes-share-owner@example.com")
    grantee = await make_user(db_session, email="notes-share-grantee@example.com")
    owner_cu = current_user_for(owner)

    note = await create_note(db_session, owner_cu, NoteCreate(body="shared note"))
    await share_note(
        db_session, owner_cu, note.id, email="notes-share-grantee@example.com", permission="read"
    )

    grantee_cu = current_user_for(grantee)
    fetched = await get_note(db_session, grantee_cu, note.id)
    assert fetched.id == note.id

    with pytest.raises(AppError) as exc_info:
        await update_note(db_session, grantee_cu, note.id, NoteUpdate(body="hacked"))
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "acl.forbidden"


# Case 49: full-text search matches on title and body.


async def test_full_text_search_matches_title_and_body(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="notes-search@example.com")
    cu = current_user_for(owner)

    matching_title = await create_note(
        db_session, cu, NoteCreate(title="Grocery list", body="milk, eggs")
    )
    matching_body = await create_note(
        db_session, cu, NoteCreate(body="remember to buy groceries later")
    )
    await create_note(db_session, cu, NoteCreate(body="totally unrelated content"))

    page = await list_notes(db_session, cu, limit=20, cursor=None, q="groceries", pinned=None)
    ids = {item.id for item in page.items}
    assert matching_body.id in ids

    page2 = await list_notes(db_session, cu, limit=20, cursor=None, q="Grocery", pinned=None)
    ids2 = {item.id for item in page2.items}
    assert matching_title.id in ids2


# Case 50: pagination returns a stable, non-overlapping sequence across pages.


async def test_pagination_stable_non_overlapping_across_pages(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="notes-paginate@example.com")
    cu = current_user_for(owner)

    created_ids = []
    for i in range(23):
        note = await create_note(db_session, cu, NoteCreate(body=f"note number {i}"))
        created_ids.append(note.id)

    seen: list = []
    cursor = None
    for _ in range(10):  # generous upper bound on page count
        page = await list_notes(db_session, cu, limit=10, cursor=cursor, q=None, pinned=None)
        seen.extend(item.id for item in page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert len(seen) == len(created_ids)
    assert len(set(seen)) == len(created_ids)
    assert set(seen) == set(created_ids)


# Case 51: purge_deleted removes only rows deleted more than 30 days ago.


async def test_purge_deleted_removes_only_old_soft_deletes(db_session: AsyncSession) -> None:
    owner = await make_user(db_session, email="notes-purge@example.com")
    cu = current_user_for(owner)

    old_note = await create_note(db_session, cu, NoteCreate(body="old deleted"))
    recent_note = await create_note(db_session, cu, NoteCreate(body="recently deleted"))
    kept_note = await create_note(db_session, cu, NoteCreate(body="not deleted"))

    now = datetime.now(UTC)
    old_row = (await db_session.execute(select(Note).where(Note.id == old_note.id))).scalar_one()
    old_row.deleted_at = now - timedelta(days=31)
    recent_row = (
        await db_session.execute(select(Note).where(Note.id == recent_note.id))
    ).scalar_one()
    recent_row.deleted_at = now - timedelta(days=5)
    await db_session.flush()

    all_ids = {old_note.id, recent_note.id, kept_note.id}
    purged_count_before = (
        await db_session.execute(select(func.count()).where(Note.id.in_(all_ids)))
    ).scalar_one()
    assert purged_count_before == 3

    await purge_deleted(db_session)
    await db_session.flush()

    # Scope this assertion to the note ids this test created: purge_deleted()
    # has no user filter (by design — it's a global maintenance sweep), so
    # other data genuinely committed elsewhere in the shared container (e.g.
    # by CLI tests, which use a real-commit session — see tests/cli/conftest.py)
    # legitimately coexists in the same table and must not be mistaken for a
    # regression here.
    remaining_ids = set(
        (await db_session.execute(select(Note.id).where(Note.id.in_(all_ids)))).scalars().all()
    )
    assert remaining_ids == {recent_note.id, kept_note.id}
