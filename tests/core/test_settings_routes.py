import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import DEFAULT_PASSWORD, make_user


async def _authed(client: httpx.AsyncClient, db_session: AsyncSession, email: str) -> None:
    await make_user(db_session, email=email)
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


async def test_get_domain_settings_defaults_empty(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "settings-get@example.com")

    response = await client.get("/api/settings/core")

    assert response.status_code == 200
    body = response.json()
    # _read_masked_panel reads raw stored values (default=None) rather than
    # applying the schema's own Pydantic field defaults.
    assert body["channels"] is None
    assert body["routing"] is None
    assert body["urls"] is None


async def test_put_domain_settings_round_trips_non_secret_field(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "settings-put@example.com")

    response = await client.put(
        "/api/settings/core",
        json={"channels": [{"id": "chan1", "label": "Chan 1", "enabled": True}]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["channels"] == [{"id": "chan1", "label": "Chan 1", "enabled": True}]

    reread = await client.get("/api/settings/core")
    assert reread.json()["channels"] == [{"id": "chan1", "label": "Chan 1", "enabled": True}]


async def test_put_domain_settings_masks_secret_field_and_preserves_unchanged(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "settings-secret@example.com")

    first = await client.put(
        "/api/settings/core", json={"urls": {"chan1": "https://example.com/hook"}}
    )
    assert first.status_code == 200
    assert first.json()["urls"] == {"chan1": "***"}

    # Sending the sentinel back unchanged must not disturb the stored value.
    second = await client.put(
        "/api/settings/core",
        json={"urls": {"chan1": "***"}, "routing": {"notes.reminder": ["chan1"]}},
    )
    assert second.status_code == 200
    assert second.json()["urls"] == {"chan1": "***"}
    assert second.json()["routing"] == {"notes.reminder": ["chan1"]}


async def test_put_unknown_field_returns_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "settings-unknown@example.com")

    response = await client.put("/api/settings/core", json={"nonexistent_field": 1})

    assert response.status_code == 422
    assert response.json()["code"] == "core.platform.validation_error"


async def test_get_unknown_domain_returns_404(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "settings-404@example.com")

    response = await client.get("/api/settings/nonexistent.domain")

    assert response.status_code == 404
    assert response.json()["code"] == "core.settings.domain_not_found"
