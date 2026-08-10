"""HTTP API — /api/files (M18-files.md §10).

GET /api/files/usage is declared BEFORE GET/HEAD /api/files/{asset_id} —
FastAPI matches in declaration order, and a `/{asset_id}` declared first
would swallow `/usage` and fail UUID parsing with a 422. Identical to the
`/api/plants/due` gotcha (plants/router.py).
"""

import uuid
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth import CurrentUser, require_admin
from disp.core.auth.dependencies import optional_user
from disp.core.db import get_session
from disp.core.errors import AppError, limiter
from disp.core.files import UsageSummary, get_file_store
from disp.core.files.sniff import SNIFFABLE_EXTENSIONS
from disp.core.files.store import FileStore
from disp.core.models import Asset

router = APIRouter(tags=["files"])


def _not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="core.files.not_found",
        title="File not found",
        detail="No such file.",
    )


def _forbidden_error() -> AppError:
    return AppError(
        status_code=403,
        code="core.files.forbidden",
        title="Forbidden",
        detail="You do not have access to this file.",
    )


def _url_expired_error() -> AppError:
    return AppError(
        status_code=403,
        code="core.files.url_expired",
        title="Link expired",
        detail="This link has expired or is invalid.",
    )


def _content_disposition(asset: Asset) -> str:
    # I6: only a positively sniffed type may ever be inline. The text family
    # is unsniffable by definition, so it always falls to attachment here —
    # that's what makes storing unsniffable types safe (M18-files.md §7.1).
    disposition = "inline" if asset.content_type in SNIFFABLE_EXTENSIONS else "attachment"
    filename = asset.original_filename or str(asset.id)
    encoded = quote(filename)
    return f"{disposition}; filename*=UTF-8''{encoded}"


@router.get("/usage", operation_id="files_usage")
async def get_usage(
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> UsageSummary:
    return await files.usage(session)


@router.head("/{asset_id}", operation_id="files_head", include_in_schema=False)
@router.get("/{asset_id}", operation_id="files_get")
@limiter.limit("300/minute")
async def get_asset(
    asset_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    files: Annotated[FileStore, Depends(get_file_store)],
    user: Annotated[CurrentUser | None, Depends(optional_user)],
    if_none_match: Annotated[str | None, Header(alias="if-none-match")] = None,
    exp: int | None = None,
    sig: str | None = None,
) -> Response:
    # Two authentication paths (§10): exp+sig is the platform's first
    # unauthenticated route — explicitly rate-limited above even though it
    # matches the global default, since it's shared by every thumbnail on a
    # page. Without exp/sig, fall back to bearer auth + ownership/admin.
    asset = await session.get(Asset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise _not_found_error()

    remaining: int | None = None
    if exp is not None or sig is not None:
        if exp is None or sig is None or not files.verify_signature(asset_id, exp=exp, sig=sig):
            # Tampered and expired both fail the same way (§9.1) — the
            # response doesn't distinguish which, so it can't leak which
            # failure mode occurred.
            raise _url_expired_error()
        remaining = max(0, exp - int(datetime.now(UTC).timestamp()))
    elif user is None or (asset.owner_user_id != user.id and not user.is_admin):
        raise _forbidden_error()

    # files_s3_native_presign's 302-redirect branch is unreachable this pass
    # — the S3 backend isn't built yet (M18-files.md §6.2 is deferred).

    etag = f'"{asset.sha256}"'
    if if_none_match is not None and if_none_match == etag:
        return Response(status_code=304)

    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(asset.created_at, usegmt=True),
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Content-Disposition": _content_disposition(asset),
        "Accept-Ranges": "none",
        "Cache-Control": (
            f"private, max-age={remaining}, immutable"
            if remaining is not None
            else "private, no-store"
        ),
    }

    if request.method == "HEAD":
        return Response(status_code=200, headers=headers, media_type=asset.content_type)

    body = await files.open(session, asset_id)
    return StreamingResponse(body, media_type=asset.content_type, headers=headers)
