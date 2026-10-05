"""HTTP API — /api/llm (M19-llm.md §11).

Deliberately one route: there is no generic "ask the model" endpoint
anywhere in this module. A generic endpoint would be an
unauthenticated-in-effect cost amplifier — any user could spend the
deployment's budget on anything — and it belongs to no module's
authorization story. LLM access reaches users only through a module's own
routes, where that module has already decided who may do what.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, require_admin
from disp.core.db import get_session
from disp.core.llm.facade import LLMFacade
from disp.core.llm.usage import UsageSummary

router = APIRouter(tags=["llm"])


def _get_llm_facade(request: Request) -> LLMFacade:
    return request.app.state.platform.llm  # type: ignore[no-any-return]


@router.get("/usage", operation_id="llm_usage")
async def get_usage(
    session: Annotated[AsyncSession, Depends(get_session)],
    llm: Annotated[LLMFacade, Depends(_get_llm_facade)],
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    since: datetime | None = None,
    call_name: str | None = None,
) -> UsageSummary:
    return await llm.usage(session, since=since, call_name=call_name)
