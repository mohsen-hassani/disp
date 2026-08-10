"""HTTP API — /api/files (M18-files.md §10)."""

import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.files.store import ACCEPT_IMAGES, AcceptSpec, StoredFile
from disp.core.models import User
from tests.factories import DEFAULT_PASSWORD, make_user

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


async def _authed(client: httpx.AsyncClient, db_session: AsyncSession, email: str) -> User:
    user = await make_user(db_session, email=email)
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return user


async def _store_asset(
    app: FastAPI,
    db_session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    data: bytes,
    accept: AcceptSpec = ACCEPT_IMAGES,
    filename: str | None = None,
) -> StoredFile:
    files = app.state.platform.files

    async def chunks() -> AsyncIterator[bytes]:
        yield data

    stored = await files.put(
        db_session,
        owner=owner_id,
        domain="plants",
        purpose="plant_photo",
        source=chunks(),
        filename=filename,
        accept=accept,
    )
    await db_session.flush()
    return stored


async def test_usage_route_is_admin_only_and_not_shadowed_by_asset_id(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # Route-ordering gotcha (§10): a `/{asset_id}` declared first would
    # swallow `/usage` and 422 trying to parse "usage" as a UUID.
    user = await _authed(client, db_session, "files-usage-admin@example.com")
    user.is_admin = True
    await db_session.flush()

    response = await client.get("/api/files/usage")

    assert response.status_code == 200
    assert "rows" in response.json()


async def test_usage_route_is_forbidden_for_non_admins(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "files-usage-nonadmin@example.com")

    response = await client.get("/api/files/usage")

    assert response.status_code == 403


async def test_signed_url_serves_bytes_without_a_session(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await make_user(db_session, email="files-signed@example.com")
    stored = await _store_asset(app, db_session, owner_id=owner.id, data=PNG_1PX)

    url = app.state.platform.files.signed_url(stored.id)
    response = await client.get(url)

    assert response.status_code == 200
    assert response.content == PNG_1PX
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["cache-control"].startswith("private, max-age=")
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_tampered_signature_is_rejected(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await make_user(db_session, email="files-tampered@example.com")
    stored = await _store_asset(app, db_session, owner_id=owner.id, data=PNG_1PX)

    url = app.state.platform.files.signed_url(stored.id)
    response = await client.get(url + "x")

    assert response.status_code == 403
    assert response.json()["code"] == "core.files.url_expired"


async def test_bearer_owner_can_fetch_without_a_signature(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await _authed(client, db_session, "files-bearer-owner@example.com")
    stored = await _store_asset(app, db_session, owner_id=owner.id, data=PNG_1PX)

    response = await client.get(f"/api/files/{stored.id}")

    assert response.status_code == 200
    assert response.content == PNG_1PX


async def test_bearer_non_owner_non_admin_is_forbidden(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await make_user(db_session, email="files-owner-2@example.com")
    stored = await _store_asset(app, db_session, owner_id=owner.id, data=PNG_1PX)
    await _authed(client, db_session, "files-stranger@example.com")

    response = await client.get(f"/api/files/{stored.id}")

    assert response.status_code == 403
    assert response.json()["code"] == "core.files.forbidden"


async def test_unauthenticated_request_without_signature_is_forbidden(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await make_user(db_session, email="files-owner-3@example.com")
    stored = await _store_asset(app, db_session, owner_id=owner.id, data=PNG_1PX)

    response = await client.get(f"/api/files/{stored.id}")

    assert response.status_code == 403


async def test_unknown_asset_is_404(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await _authed(client, db_session, "files-404@example.com")

    response = await client.get(f"/api/files/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "core.files.not_found"


async def test_if_none_match_returns_304(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await make_user(db_session, email="files-etag@example.com")
    stored = await _store_asset(app, db_session, owner_id=owner.id, data=PNG_1PX)
    url = app.state.platform.files.signed_url(stored.id)

    first = await client.get(url)
    etag = first.headers["etag"]

    second = await client.get(url, headers={"If-None-Match": etag})

    assert second.status_code == 304


async def test_text_family_asset_is_never_served_inline(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await make_user(db_session, email="files-text@example.com")
    stored = await _store_asset(
        app,
        db_session,
        owner_id=owner.id,
        data=b"<html><body>hi</body></html>",
        accept=AcceptSpec(frozenset({"text/html"}), 1000),
    )
    url = app.state.platform.files.signed_url(stored.id)

    response = await client.get(url)

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment")


async def test_head_returns_headers_without_a_body(
    client: httpx.AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    owner = await make_user(db_session, email="files-head@example.com")
    stored = await _store_asset(app, db_session, owner_id=owner.id, data=PNG_1PX)
    url = app.state.platform.files.signed_url(stored.id)

    response = await client.head(url)

    assert response.status_code == 200
    assert response.content == b""
    assert "etag" in response.headers
