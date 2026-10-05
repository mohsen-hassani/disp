"""HTTP API — /api/files (M18-files.md §10).

Only the admin usage report. Bytes are never served through the API: links
are presigned URLs that point straight at the bucket (§9), and uploads go
through the owning module's own route.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, require_admin
from disp.core.db import get_session
from disp.core.files.store import FileStore, UsageSummary, get_file_store

router = APIRouter(tags=["files"])


@router.get("/usage", operation_id="files_usage")
async def get_usage(
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> UsageSummary:
    return await files.usage(session)
