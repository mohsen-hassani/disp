"""HTTP API — /api/files (M18-files.md §10): the admin usage report only."""

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.models import User
from tests.factories import DEFAULT_PASSWORD, make_user


async def _authed(client: httpx.AsyncClient, session: AsyncSession, email: str) -> User:
    user = await make_user(session, email=email)
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return user


async def test_usage_route_is_admin_only(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await _authed(client, db_session, "files-usage-admin@example.com")
    user.is_admin = True
    await db_session.flush()

    response = await client.get("/api/files/usage")

    assert response.status_code == 200
    assert set(response.json()) == {"rows", "total_count", "total_bytes"}


async def test_usage_route_is_forbidden_for_non_admins(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "files-usage-nonadmin@example.com")
    assert (await client.get("/api/files/usage")).status_code == 403


async def test_bytes_are_never_served_through_the_api(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """v1's streaming GET /api/files/{id} is gone: links point at the bucket."""
    await _authed(client, db_session, "files-no-stream@example.com")
    assert (await client.get(f"/api/files/{uuid.uuid4()}")).status_code in {404, 405}
