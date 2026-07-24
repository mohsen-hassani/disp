import asyncio
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from disp import __version__
from disp.core.db import get_session
from disp.core.registry import Registry

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])

DATABASE_CHECK_TIMEOUT_SECONDS = 2


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    version: str
    database: str
    modules: list[str]
    worker_last_seen: datetime | None


class LiveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


async def _database_status(session: AsyncSession) -> str:
    try:
        async with asyncio.timeout(DATABASE_CHECK_TIMEOUT_SECONDS):
            await session.execute(text("SELECT 1"))
        return "ok"
    except (TimeoutError, SQLAlchemyError, OSError) as exc:
        logger.error("health_database_check_failed", exc_info=exc)
        return "error"


async def _worker_last_seen(session: AsyncSession) -> datetime | None:
    try:
        result = await session.execute(
            text("SELECT MAX(at) FROM procrastinate_events WHERE type = 'succeeded'")
        )
        return result.scalar_one_or_none()
    except (SQLAlchemyError, OSError):
        return None


@router.get(
    "",
    response_model=HealthResponse,
    status_code=200,
    summary="Overall platform health",
    operation_id="health_check",
    responses={503: {"description": "Degraded: the database is unreachable"}},
)
async def health(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthResponse:
    database_status = await _database_status(session)
    worker_last_seen = await _worker_last_seen(session) if database_status == "ok" else None
    registry: Registry = request.app.state.registry
    modules = [dm.manifest.domain for dm in registry.modules]

    status = "ok" if database_status == "ok" else "degraded"
    if status != "ok":
        response.status_code = 503

    return HealthResponse(
        status=status,
        version=__version__,
        database=database_status,
        modules=modules,
        worker_last_seen=worker_last_seen,
    )


@router.get(
    "/live",
    response_model=LiveResponse,
    status_code=200,
    summary="Liveness probe (no database access)",
    operation_id="health_live",
)
async def health_live() -> LiveResponse:
    return LiveResponse(status="ok")
