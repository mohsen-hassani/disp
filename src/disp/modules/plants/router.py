from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, current_user
from disp.core.db import get_session
from disp.core.files import FileStore, get_file_store
from disp.core.pagination import Page
from disp.modules.plants import service
from disp.modules.plants.schemas import (
    CalendarOut,
    CareIntervalCreate,
    CareIntervalOut,
    CareIntervalUpdate,
    CareLogOut,
    CompleteRequest,
    CompleteResult,
    DueSummary,
    PlantCreate,
    PlantDetailOut,
    PlantOut,
    PlantUpdate,
)

router = APIRouter()

# Annotated to match FastAPI's `responses=` parameter type; without it mypy
# infers dict[int, dict[str, str]] and rejects every ** unpacking below.
_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {404: {"description": "Plant not found or not visible to the caller"}}
_FORBIDDEN: _Responses = {
    403: {"description": "Caller can see the plant but lacks write permission"}
}


# NOTE: the two literal paths below MUST stay above "/{plant_id}" — FastAPI
# matches in declaration order, and a "/{plant_id}" declared first would
# swallow "/due" and fail UUID parsing with a 422.


@router.get(
    "",
    response_model=Page[PlantOut],
    status_code=200,
    summary="List the caller's plants",
    operation_id="plants_list",
)
async def list_plants(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[PlantOut]:
    return await service.list_plants(session, user, limit=limit, cursor=cursor, q=q, files=files)


@router.post(
    "",
    response_model=PlantOut,
    status_code=201,
    summary="Create a plant",
    operation_id="plants_create",
)
async def create_plant(
    payload: PlantCreate,
    response: Response,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
) -> PlantOut:
    plant = await service.create_plant(session, user, payload, files=files)
    response.headers["Location"] = f"/api/plants/{plant.id}"
    return plant


@router.get(
    "/due",
    response_model=DueSummary,
    status_code=200,
    summary="Care actions due today across all plants",
    operation_id="plants_due",
)
async def due_today(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    lookahead_days: Annotated[int, Query(ge=0, le=30)] = 0,
) -> DueSummary:
    return await service.due_summary(session, user, lookahead_days=lookahead_days)


@router.get(
    "/calendar",
    response_model=CalendarOut,
    status_code=200,
    summary="Completed and scheduled care for one month",
    operation_id="plants_calendar",
    responses={400: {"description": "month is not formatted as YYYY-MM"}},
)
async def month_calendar(
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")],
) -> CalendarOut:
    return await service.month_calendar(session, user, month=month)


@router.get(
    "/{plant_id}",
    response_model=PlantDetailOut,
    status_code=200,
    summary="Read a plant with its care intervals",
    operation_id="plants_get",
    responses={**_NOT_FOUND},
)
async def get_plant(
    plant_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
) -> PlantDetailOut:
    return await service.get_plant(session, user, plant_id, files=files)


@router.patch(
    "/{plant_id}",
    response_model=PlantOut,
    status_code=200,
    summary="Partially update a plant",
    operation_id="plants_update",
    responses={**_FORBIDDEN, **_NOT_FOUND},
)
async def update_plant(
    plant_id: UUID,
    payload: PlantUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
) -> PlantOut:
    return await service.update_plant(session, user, plant_id, payload, files=files)


@router.delete(
    "/{plant_id}",
    status_code=204,
    summary="Soft-delete a plant",
    operation_id="plants_delete",
    responses={**_FORBIDDEN, **_NOT_FOUND},
)
async def delete_plant(
    plant_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await service.delete_plant(session, user, plant_id)
    return Response(status_code=204)


@router.get(
    "/{plant_id}/image",
    status_code=302,
    summary="Fetch a plant's photo",
    operation_id="plants_get_image",
    responses={
        302: {"description": "Redirect to a signed /api/files URL"},
        404: {"description": "Plant not visible to the caller, or it has no photo"},
    },
)
async def get_plant_image(
    plant_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
) -> RedirectResponse:
    url = await service.plant_image_redirect_url(session, user, plant_id, files=files)
    return RedirectResponse(url, status_code=302)


@router.put(
    "/{plant_id}/image",
    response_model=PlantOut,
    status_code=200,
    summary="Upload or replace a plant's photo",
    operation_id="plants_set_image",
    responses={
        **_FORBIDDEN,
        **_NOT_FOUND,
        413: {"description": "Image exceeds the configured size limit"},
        415: {"description": "File is not a supported image type (core.files.unsupported_type)"},
    },
)
async def set_plant_image(
    plant_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
    file: Annotated[UploadFile, File()],
) -> PlantOut:
    return await service.set_plant_image(
        session, user, plant_id, source=file, filename=file.filename, files=files
    )


@router.delete(
    "/{plant_id}/image",
    status_code=204,
    summary="Remove a plant's photo",
    operation_id="plants_delete_image",
    responses={**_FORBIDDEN, **_NOT_FOUND},
)
async def delete_plant_image(
    plant_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
) -> Response:
    await service.clear_plant_image(session, user, plant_id, files=files)
    return Response(status_code=204)


@router.get(
    "/{plant_id}/history",
    response_model=list[CareLogOut],
    status_code=200,
    summary="Recent completed care for one plant",
    operation_id="plants_history",
    responses={**_NOT_FOUND},
)
async def list_history(
    plant_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CareLogOut]:
    return await service.list_history(session, user, plant_id, limit=limit)


@router.post(
    "/{plant_id}/intervals",
    response_model=CareIntervalOut,
    status_code=201,
    summary="Add a recurring care interval to a plant",
    operation_id="plants_add_interval",
    responses={
        400: {"description": "last_done_on is in the future"},
        **_FORBIDDEN,
        **_NOT_FOUND,
    },
)
async def add_interval(
    plant_id: UUID,
    payload: CareIntervalCreate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CareIntervalOut:
    return await service.add_interval(session, user, plant_id, payload)


@router.patch(
    "/{plant_id}/intervals/{interval_id}",
    response_model=CareIntervalOut,
    status_code=200,
    summary="Update a care interval",
    operation_id="plants_update_interval",
    responses={**_FORBIDDEN, **_NOT_FOUND},
)
async def update_interval(
    plant_id: UUID,
    interval_id: UUID,
    payload: CareIntervalUpdate,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CareIntervalOut:
    return await service.update_interval(session, user, plant_id, interval_id, payload)


@router.delete(
    "/{plant_id}/intervals/{interval_id}",
    status_code=204,
    summary="Delete a care interval",
    operation_id="plants_delete_interval",
    responses={**_FORBIDDEN, **_NOT_FOUND},
)
async def delete_interval(
    plant_id: UUID,
    interval_id: UUID,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    await service.delete_interval(session, user, plant_id, interval_id)
    return Response(status_code=204)


@router.post(
    "/{plant_id}/intervals/{interval_id}/complete",
    response_model=CompleteResult,
    status_code=201,
    summary="Mark a care action done and reschedule it",
    operation_id="plants_complete_interval",
    responses={
        400: {"description": "completed_on is in the future or too far in the past"},
        **_FORBIDDEN,
        **_NOT_FOUND,
    },
)
async def complete_interval(
    plant_id: UUID,
    interval_id: UUID,
    payload: CompleteRequest,
    user: Annotated[CurrentUser, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CompleteResult:
    return await service.complete_interval(session, user, plant_id, interval_id, payload)
