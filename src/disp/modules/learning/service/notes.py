"""§14: notes. Mirrors `courses.py`'s resolve -> authorize -> CRUD ->
cursor-page shape. Notes touch no LLM call and affect no score (§14) — this
file is the one service module in the module with no `platform.llm`
dependency anywhere in it.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from disp.core.auth import CurrentUser
from disp.core.errors import AppError
from disp.core.pagination import Page, decode_cursor, encode_cursor
from disp.modules.learning.models import Note
from disp.modules.learning.schemas import NoteCreate, NoteOut, NoteUpdate
from disp.modules.learning.service.courses import _authorize, _resolve_course


def _note_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="modules.learning.note_not_found",
        title="Note not found",
        detail="The note does not exist or is not visible to you.",
    )


def _invalid_anchor_error() -> AppError:
    return AppError(
        status_code=400,
        code="modules.learning.invalid_note_anchor",
        title="Invalid note anchor",
        detail="A note may have at most one anchor (path item, topic, or source section).",
    )


def _to_out(note: Note) -> NoteOut:
    return NoteOut(
        id=note.id,
        course_id=note.course_id,
        label=note.label,
        body=note.body,
        path_item_id=note.path_item_id,
        topic_id=note.topic_id,
        source_section_id=note.source_section_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def _resolve_note(session: AsyncSession, note_id: UUID) -> Note:
    note = await session.get(Note, note_id)
    if note is None or note.deleted_at is not None:
        raise _note_not_found_error()
    return note


def _anchor_count(*anchors: UUID | None) -> int:
    return sum(1 for a in anchors if a is not None)


async def create_note(
    session: AsyncSession, user: CurrentUser, course_id: UUID, payload: NoteCreate
) -> NoteOut:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "update")

    if _anchor_count(payload.path_item_id, payload.topic_id, payload.source_section_id) > 1:
        # Belt-and-suspenders: `ck_note_single_anchor` (§14) enforces this at
        # the database too, but a clean 400 here beats an IntegrityError.
        raise _invalid_anchor_error()

    note = Note(
        course_id=course_id,
        user_id=user.id,
        label=payload.label,
        body=payload.body,
        path_item_id=payload.path_item_id,
        topic_id=payload.topic_id,
        source_section_id=payload.source_section_id,
    )
    session.add(note)
    await session.flush()
    return _to_out(note)


async def update_note(
    session: AsyncSession, user: CurrentUser, note_id: UUID, payload: NoteUpdate
) -> NoteOut:
    note = await _resolve_note(session, note_id)
    await _resolve_course(session, note.course_id)
    await _authorize(session, user, note.course_id, "update")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(note, field, value)
    note.updated_at = datetime.now(UTC)
    return _to_out(note)


async def delete_note(session: AsyncSession, user: CurrentUser, note_id: UUID) -> None:
    note = await _resolve_note(session, note_id)
    await _resolve_course(session, note.course_id)
    await _authorize(session, user, note.course_id, "update")
    now = datetime.now(UTC)
    note.deleted_at = now
    note.updated_at = now


async def list_notes(
    session: AsyncSession,
    user: CurrentUser,
    course_id: UUID,
    *,
    label: str | None,
    path_item_id: UUID | None,
    limit: int,
    cursor: str | None,
) -> Page[NoteOut]:
    await _resolve_course(session, course_id)
    await _authorize(session, user, course_id, "read")

    conditions: list[ColumnElement[bool]] = [
        Note.course_id == course_id,
        Note.deleted_at.is_(None),
    ]
    if label is not None:
        conditions.append(Note.label == label)
    if path_item_id is not None:
        conditions.append(Note.path_item_id == path_item_id)

    if cursor:
        cursor_data = decode_cursor(cursor)
        try:
            seek_id = UUID(cursor_data.id)
        except ValueError as exc:
            raise AppError(
                status_code=400,
                code="core.pagination.invalid_cursor",
                title="Invalid cursor",
                detail="The pagination cursor could not be decoded.",
            ) from exc
        seek_note = await session.get(Note, seek_id)
        if seek_note is None:
            raise AppError(
                status_code=400,
                code="core.pagination.invalid_cursor",
                title="Invalid cursor",
                detail="The pagination cursor could not be decoded.",
            )
        conditions.append(
            tuple_(Note.created_at, Note.id)
            < tuple_(literal(seek_note.created_at), literal(seek_note.id))
        )

    stmt = (
        select(Note)
        .where(*conditions)
        .order_by(Note.created_at.desc(), Note.id.desc())
        .limit(limit + 1)
    )
    rows = list((await session.execute(stmt)).scalars())

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return Page[NoteOut](
        items=[_to_out(row) for row in rows], next_cursor=next_cursor, has_more=has_more
    )
