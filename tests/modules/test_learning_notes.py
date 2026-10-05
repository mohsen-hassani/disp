"""M20 §14 (Phase 7): notes — CRUD, the single-anchor rule, cursor
pagination, and label/anchor filtering. Notes touch no LLM call, so this
file runs entirely against the ordinary per-test-rollback `db_session`.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser
from disp.core.errors import AppError
from disp.modules.learning.models import Course, Note, PathItem
from disp.modules.learning.schemas import CourseCreate, NoteCreate, NoteUpdate
from disp.modules.learning.service.courses import create_course
from disp.modules.learning.service.notes import create_note, delete_note, list_notes, update_note
from tests.factories import current_user_for, make_user


async def _course(session: AsyncSession, email: str) -> tuple[CurrentUser, Course]:
    user = await make_user(session, email=email)
    cu = current_user_for(user)
    course_out = await create_course(session, cu, CourseCreate(title="Design Patterns"))
    course = (await session.execute(select(Course).where(Course.id == course_out.id))).scalar_one()
    return cu, course


async def test_create_note_with_no_anchor_belongs_to_the_course(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-notes-general@example.com")
    note = await create_note(
        db_session, cu, course.id, NoteCreate(label="note", body="General thought")
    )
    assert note.path_item_id is None
    assert note.topic_id is None
    assert note.source_section_id is None


async def test_create_note_with_one_anchor_succeeds(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-notes-anchored@example.com")
    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()

    note = await create_note(
        db_session,
        cu,
        course.id,
        NoteCreate(label="todo", body="Review this", path_item_id=item.id),
    )
    assert note.path_item_id == item.id


async def test_create_note_with_two_anchors_is_rejected_before_hitting_the_db(
    db_session: AsyncSession,
) -> None:
    cu, course = await _course(db_session, "learning-notes-multianchor@example.com")
    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()

    with pytest.raises(AppError) as exc_info:
        await create_note(
            db_session,
            cu,
            course.id,
            NoteCreate(label="note", body="x", path_item_id=item.id, topic_id=uuid4()),
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "modules.learning.invalid_note_anchor"


async def test_two_anchors_via_direct_sql_violates_the_db_constraint(
    db_session: AsyncSession,
) -> None:
    """§14: the single-anchor rule is `ck_note_single_anchor`, a database
    constraint, not just a service-layer check — bypass the service and
    confirm the database itself refuses the row."""
    cu, course = await _course(db_session, "learning-notes-constraint@example.com")
    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()

    note = Note(
        course_id=course.id,
        user_id=cu.id,
        label="note",
        body="x",
        path_item_id=item.id,
        topic_id=uuid4(),
    )
    db_session.add(note)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_update_note_changes_label_and_body(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-notes-update@example.com")
    note = await create_note(db_session, cu, course.id, NoteCreate(label="note", body="Original"))

    updated = await update_note(db_session, cu, note.id, NoteUpdate(label="todo", body="Updated"))
    assert updated.label == "todo"
    assert updated.body == "Updated"


async def test_delete_note_soft_deletes_then_hidden_from_list(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-notes-delete@example.com")
    note = await create_note(db_session, cu, course.id, NoteCreate(label="note", body="Gone soon"))

    await delete_note(db_session, cu, note.id)
    await db_session.flush()

    row = (await db_session.execute(select(Note).where(Note.id == note.id))).scalar_one()
    assert row.deleted_at is not None  # soft-deleted, not removed

    page = await list_notes(
        db_session, cu, course.id, label=None, path_item_id=None, limit=20, cursor=None
    )
    assert note.id not in {n.id for n in page.items}


async def test_list_notes_filters_by_label_and_path_item(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-notes-filter@example.com")
    item = PathItem(course_id=course.id, tier="beginner", order_index=0, title="Lesson")
    db_session.add(item)
    await db_session.flush()

    general_note = await create_note(
        db_session, cu, course.id, NoteCreate(label="note", body="General")
    )
    todo_note = await create_note(
        db_session, cu, course.id, NoteCreate(label="todo", body="Do this", path_item_id=item.id)
    )

    by_label = await list_notes(
        db_session, cu, course.id, label="todo", path_item_id=None, limit=20, cursor=None
    )
    assert {n.id for n in by_label.items} == {todo_note.id}

    by_anchor = await list_notes(
        db_session, cu, course.id, label=None, path_item_id=item.id, limit=20, cursor=None
    )
    assert {n.id for n in by_anchor.items} == {todo_note.id}

    unfiltered = await list_notes(
        db_session, cu, course.id, label=None, path_item_id=None, limit=20, cursor=None
    )
    assert {n.id for n in unfiltered.items} == {general_note.id, todo_note.id}


async def test_list_notes_paginates_stably(db_session: AsyncSession) -> None:
    cu, course = await _course(db_session, "learning-notes-paginate@example.com")
    created_ids = []
    for i in range(15):
        note = await create_note(db_session, cu, course.id, NoteCreate(label="note", body=f"n{i}"))
        created_ids.append(note.id)

    seen: list = []
    cursor = None
    for _ in range(10):
        page = await list_notes(
            db_session, cu, course.id, label=None, path_item_id=None, limit=5, cursor=cursor
        )
        seen.extend(n.id for n in page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert len(seen) == len(created_ids)
    assert set(seen) == set(created_ids)


async def test_notes_on_unreadable_course_returns_404(db_session: AsyncSession) -> None:
    _cu, course = await _course(db_session, "learning-notes-owner@example.com")
    stranger = await make_user(db_session, email="learning-notes-stranger@example.com")

    with pytest.raises(AppError) as exc_info:
        await list_notes(
            db_session,
            current_user_for(stranger),
            course.id,
            label=None,
            path_item_id=None,
            limit=20,
            cursor=None,
        )
    assert exc_info.value.status_code == 404
