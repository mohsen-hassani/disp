from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, current_user
from disp.core.db import get_session
from disp.core.pagination import Page
from disp.modules.notes import service
from disp.modules.notes.schemas import NoteCreate, NoteOut, NoteUpdate, ShareRequest

router = APIRouter()


@router.get(
    "",
    response_model=Page[NoteOut],
    status_code=200,
    summary="List the caller's notes",
    operation_id="notes_list",
)
async def list_notes(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    pinned: Annotated[bool | None, Query()] = None,
) -> Page[NoteOut]:
    return await service.list_notes(session, user, limit=limit, cursor=cursor, q=q, pinned=pinned)


@router.post(
    "",
    response_model=NoteOut,
    status_code=201,
    summary="Create a note",
    operation_id="notes_create",
)
async def create_note(
    payload: NoteCreate,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteOut:
    note = await service.create_note(session, user, payload)
    response.headers["Location"] = f"/api/notes/{note.id}"
    return note


@router.get(
    "/{note_id}",
    response_model=NoteOut,
    status_code=200,
    summary="Read a single note",
    operation_id="notes_get",
    responses={404: {"description": "Note not found or not visible to the caller"}},
)
async def get_note(
    note_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteOut:
    return await service.get_note(session, user, note_id)


@router.patch(
    "/{note_id}",
    response_model=NoteOut,
    status_code=200,
    summary="Partially update a note",
    operation_id="notes_update",
    responses={
        403: {"description": "Caller can see the note but lacks write permission"},
        404: {"description": "Note not found or not visible to the caller"},
    },
)
async def update_note(
    note_id: UUID,
    payload: NoteUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> NoteOut:
    return await service.update_note(session, user, note_id, payload)


@router.delete(
    "/{note_id}",
    status_code=204,
    summary="Soft-delete a note",
    operation_id="notes_delete",
    responses={
        403: {"description": "Caller can see the note but lacks write permission"},
        404: {"description": "Note not found, not visible, or already deleted"},
    },
)
async def delete_note(
    note_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await service.delete_note(session, user, note_id)
    return Response(status_code=204)


@router.post(
    "/{note_id}/share",
    status_code=204,
    summary="Grant another user access to a note",
    operation_id="notes_share",
    responses={
        400: {"description": "Cannot share a note with yourself"},
        403: {"description": "Caller can see the note but is not its owner"},
        404: {"description": "Note or target user not found"},
    },
)
async def share_note(
    note_id: UUID,
    payload: ShareRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await service.share_note(
        session, user, note_id, email=payload.email, permission=payload.permission
    )
    return Response(status_code=204)
