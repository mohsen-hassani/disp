import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.oidc import resolve_external_token
from tests.factories import DEFAULT_PASSWORD, make_user


async def _authed(
    client: httpx.AsyncClient, db_session: AsyncSession, email: str
) -> httpx.AsyncClient:
    await make_user(db_session, email=email)
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


# Case 52: GET /health returns ok with a live database.


async def test_health_returns_ok_with_live_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert "notes" in body["modules"]


# Case 53: GET /api/dashboard/tiles renders the notes tile; a provider that
# raises yields the fallback tile rather than a 500.


async def test_dashboard_tiles_renders_notes_tile(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "dashboard-tiles@example.com")

    response = await client.get("/api/dashboard/tiles")

    assert response.status_code == 200
    tiles = response.json()["tiles"]
    keys = {tile["key"] for tile in tiles}
    assert "notes.latest" in keys


async def test_dashboard_tile_provider_raising_yields_fallback(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _authed(client, db_session, "dashboard-fallback@example.com")

    async def _boom(ctx: object) -> None:
        raise RuntimeError("tile provider exploded")

    original_tile_provider_for = app.state.registry.tile_provider_for
    monkeypatch.setattr(app.state.registry, "tile_provider_for", lambda key: _boom)

    try:
        response = await client.get("/api/dashboard/tiles")
        assert response.status_code == 200
        tiles = response.json()["tiles"]
        notes_tile = next(t for t in tiles if t["key"] == "notes.latest")
        assert notes_tile["empty_text"] == "This tile failed to load"
    finally:
        monkeypatch.setattr(app.state.registry, "tile_provider_for", original_tile_provider_for)


# Case 54: GET /api/dashboard/tiles/{unknown} returns 404.


async def test_dashboard_unknown_tile_returns_404(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "dashboard-404@example.com")

    response = await client.get("/api/dashboard/tiles/nonexistent.tile")

    assert response.status_code == 404
    assert response.json()["code"] == "dashboard.tile_not_found"


# Case 55: every route in the OpenAPI document has a unique operation_id.


def test_every_route_has_unique_operation_id(app: FastAPI) -> None:
    schema = app.openapi()
    operation_ids: list[str] = []
    for path_item in schema["paths"].values():
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                operation_ids.append(operation["operationId"])

    assert len(operation_ids) == len(set(operation_ids))
    assert len(operation_ids) > 0


# Case 56: oidc.resolve_external_token raises NotImplementedError.


async def test_oidc_resolve_external_token_raises_not_implemented(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(NotImplementedError):
        await resolve_external_token("some-token", db_session)  # type: ignore[arg-type]
