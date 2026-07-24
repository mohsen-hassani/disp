from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from disp.core.auth import CurrentUser, Permission, can, grant, readable_ids
from disp.core.errors import AppError
from disp.core.events import publish_after_commit
from disp.core.models import User
from disp.core.pagination import Page, decode_cursor, encode_cursor
from disp.modules.notes.events import NoteCreated, NoteDeleted, NoteUpdated
from disp.modules.notes.models import Note
from disp.modules.notes.schemas import NoteCreate, NoteOut, NoteUpdate

RESOURCE_TYPE = "notes.note"
PURGE_AFTER_DAYS = 30


def _not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="notes.not_found",
        title="Note not found",
        detail="The note does not exist or is not visible to you.",
    )


def _to_out(note: Note) -> NoteOut:
    return NoteOut(
        id=note.id,
        title=note.title,
        body=note.body,
        pinned=note.pinned,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def _resolve_note(session: AsyncSession, note_id: UUID) -> Note:
    note = await session.get(Note, note_id)
    if note is None or note.deleted_at is not None:
        raise _not_found_error()
    return note


async def _authorize(session: AsyncSession, user: CurrentUser, note_id: UUID, action: str) -> None:
    """Resolve-then-require with existence hidden for unreadable notes (S9):
    a caller who can't even read the note gets 404, never 403. A caller who
    can read it but lacks the specific permission for `action` gets 403."""
    if await can(session, user, action, RESOURCE_TYPE, str(note_id)):
        return
    if action == "read" or not await can(session, user, "read", RESOURCE_TYPE, str(note_id)):
        raise _not_found_error()
    raise AppError(
        status_code=403,
        code="acl.forbidden",
        title="Forbidden",
        detail="You do not have permission to perform this action.",
    )


async def list_notes(
    session: AsyncSession,
    user: CurrentUser,
    *,
    limit: int,
    cursor: str | None,
    q: str | None,
    pinned: bool | None,
) -> Page[NoteOut]:
    ids = await readable_ids(session, user_id=user.id, resource_type=RESOURCE_TYPE)
    if not ids:
        return Page[NoteOut](items=[], next_cursor=None, has_more=False)

    note_ids = [UUID(resource_id) for resource_id in ids]

    conditions: list[ColumnElement[bool]] = [Note.id.in_(note_ids), Note.deleted_at.is_(None)]
    if pinned is not None:
        conditions.append(Note.pinned.is_(pinned))
    if q:
        search_vector = func.to_tsvector("simple", func.coalesce(Note.title, "") + " " + Note.body)
        conditions.append(search_vector.op("@@")(func.plainto_tsquery("simple", q)))

    if cursor:
        cursor_data = decode_cursor(cursor)
        try:
            seek_id = UUID(cursor_data.id)
        except ValueError as exc:
            raise AppError(
                status_code=400,
                code="pagination.invalid_cursor",
                title="Invalid cursor",
                detail="The pagination cursor could not be decoded.",
            ) from exc
        seek_note = await session.get(Note, seek_id)
        if seek_note is None:
            raise AppError(
                status_code=400,
                code="pagination.invalid_cursor",
                title="Invalid cursor",
                detail="The pagination cursor could not be decoded.",
            )
        conditions.append(
            tuple_(Note.pinned, Note.created_at, Note.id)
            < tuple_(
                literal(seek_note.pinned),
                literal(seek_note.created_at),
                literal(seek_note.id),
            )
        )

    stmt = (
        select(Note)
        .where(*conditions)
        .order_by(Note.pinned.desc(), Note.created_at.desc(), Note.id.desc())
        .limit(limit + 1)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars())

    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return Page[NoteOut](
        items=[_to_out(row) for row in rows], next_cursor=next_cursor, has_more=has_more
    )


async def get_note(session: AsyncSession, user: CurrentUser, note_id: UUID) -> NoteOut:
    note = await _resolve_note(session, note_id)
    await _authorize(session, user, note_id, "read")
    return _to_out(note)


async def create_note(session: AsyncSession, user: CurrentUser, payload: NoteCreate) -> NoteOut:
    note = Note(user_id=user.id, title=payload.title, body=payload.body, pinned=payload.pinned)
    session.add(note)
    await session.flush()

    await grant(
        session,
        resource_type=RESOURCE_TYPE,
        resource_id=str(note.id),
        user_id=user.id,
        permission=Permission.OWNER,
        granted_by=user.id,
    )
    publish_after_commit(session, NoteCreated(note_id=note.id, user_id=user.id, title=note.title))

    return _to_out(note)


async def update_note(
    session: AsyncSession, user: CurrentUser, note_id: UUID, payload: NoteUpdate
) -> NoteOut:
    note = await _resolve_note(session, note_id)
    await _authorize(session, user, note_id, "update")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(note, field, value)
    note.updated_at = datetime.now(UTC)

    publish_after_commit(session, NoteUpdated(note_id=note.id, user_id=user.id))
    return _to_out(note)


async def delete_note(session: AsyncSession, user: CurrentUser, note_id: UUID) -> None:
    note = await _resolve_note(session, note_id)
    await _authorize(session, user, note_id, "delete")

    now = datetime.now(UTC)
    note.deleted_at = now
    note.updated_at = now

    publish_after_commit(session, NoteDeleted(note_id=note.id, user_id=user.id))


async def share_note(
    session: AsyncSession,
    user: CurrentUser,
    note_id: UUID,
    *,
    email: str,
    permission: str,
) -> None:
    await _resolve_note(session, note_id)
    await _authorize(session, user, note_id, "share")

    if email.strip().lower() == user.email.strip().lower():
        raise AppError(
            status_code=400,
            code="notes.cannot_share_with_self",
            title="Cannot share with yourself",
            detail="You cannot share a note with your own account.",
        )

    result = await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    target_user = result.scalar_one_or_none()
    if target_user is None:
        raise AppError(
            status_code=404,
            code="notes.user_not_found",
            title="User not found",
            detail="No user is registered with that email address.",
        )

    await grant(
        session,
        resource_type=RESOURCE_TYPE,
        resource_id=str(note_id),
        user_id=target_user.id,
        permission=Permission(permission),
        granted_by=user.id,
    )


async def purge_deleted(session: AsyncSession) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=PURGE_AFTER_DAYS)
    result = await session.execute(
        sa_delete(Note).where(Note.deleted_at.is_not(None), Note.deleted_at < cutoff)
    )
    return cast("CursorResult[Any]", result).rowcount
