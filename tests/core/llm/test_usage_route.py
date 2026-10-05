"""HTTP API — GET /api/llm/usage (M19-llm.md §11)."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.llm.usage import write_call
from disp.core.models import User
from tests.factories import DEFAULT_PASSWORD, make_user


async def _authed(
    client: httpx.AsyncClient, db_session: AsyncSession, email: str, **kwargs: object
) -> User:
    user = await make_user(db_session, email=email, **kwargs)
    await db_session.flush()
    await db_session.commit()
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return user


async def test_usage_route_requires_admin(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "not-admin@example.com", is_admin=False)
    response = await client.get("/api/llm/usage")
    assert response.status_code == 403


async def test_usage_route_returns_summary_for_admin(
    client: httpx.AsyncClient, db_session: AsyncSession, session_maker: object
) -> None:
    await write_call(
        session_maker,  # type: ignore[arg-type]
        user_id=None,
        call_name="learning.explain",
        model="claude-opus-5",
        input_tokens=10,
        cached_read_tokens=0,
        output_tokens=5,
        latency_ms=1,
        outcome="ok",
        error_code=None,
    )
    await _authed(client, db_session, "admin@example.com", is_admin=True)

    response = await client.get("/api/llm/usage", params={"call_name": "learning.explain"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_calls"] == 1
    assert body["rows"][0]["call_name"] == "learning.explain"
