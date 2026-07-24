import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.config import get_settings
from tests.factories import DEFAULT_PASSWORD, make_user

CSRF_HEADERS = {"X-Requested-With": "disp"}


async def _login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_refresh_with_no_cookie_returns_401(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_refresh_token"


async def test_refresh_with_unknown_token_returns_401(client: httpx.AsyncClient) -> None:
    client.cookies.set("disp_refresh", "totally-unknown-refresh-token")
    response = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_refresh_token"


async def test_refresh_for_disabled_account_returns_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="refresh-disabled@example.com")
    await client.post("/api/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD})

    user.is_active = False
    await db_session.flush()

    response = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
    assert response.status_code == 403
    assert response.json()["code"] == "auth.account_disabled"


async def test_revoke_unknown_token_returns_404(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="revoke-404@example.com")
    headers = await _login(client, user.email)

    response = await client.delete(f"/api/auth/tokens/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "auth.token_not_found"


async def test_create_invite_for_existing_user_returns_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await make_user(db_session, email="admin-existinginvite@example.com", is_admin=True)
    await make_user(db_session, email="already-a-user@example.com")
    headers = await _login(client, admin.email)

    response = await client.post(
        "/api/auth/invites",
        json={"email": "already-a-user@example.com", "is_admin": False},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "auth.user_exists"


async def test_accept_invite_with_unknown_token_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/accept-invite",
        json={"token": "no-such-token", "display_name": "X", "password": "a-decent-password-1"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "auth.invite_not_found"


async def test_accept_invite_weak_password_returns_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await make_user(db_session, email="admin-weakpw@example.com", is_admin=True)
    headers = await _login(client, admin.email)

    invite = await client.post(
        "/api/auth/invites",
        json={"email": "weakpw-invitee@example.com", "is_admin": False},
        headers=headers,
    )
    token = invite.json()["token"]

    response = await client.post(
        "/api/auth/accept-invite",
        json={"token": token, "display_name": "X", "password": "short"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "auth.password_policy"


async def test_change_password_wrong_current_password_returns_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="pwchange-wrong@example.com")
    headers = await _login(client, user.email)

    response = await client.post(
        "/api/auth/password",
        json={"current_password": "not-the-right-password", "new_password": "a-decent-password-1"},
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_credentials"


async def test_change_password_weak_new_password_returns_422(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="pwchange-weak@example.com")
    headers = await _login(client, user.email)

    response = await client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "short"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "auth.password_policy"


async def test_change_password_without_refresh_cookie_present(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # Authenticate via a bare Authorization header, never hitting /login, so
    # no refresh cookie is ever set on this client — exercises the "no
    # cookie" branch of change_password's except_family_id resolution.
    from disp.core.auth.tokens import create_access_token

    user = await make_user(db_session, email="pwchange-nocookie@example.com")
    await db_session.flush()
    settings = get_settings()
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=settings.access_token_ttl_seconds,
    )

    response = await client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "a-decent-password-1"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204


async def test_login_rate_limit_triggers_429(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutate the ALREADY-CACHED Settings singleton's attribute directly,
    # rather than the env var + get_settings.cache_clear() pattern used
    # elsewhere (e.g. test_registry.py): get_settings() is an lru_cache
    # shared by the whole process, and clearing/rebuilding it here raced
    # with other tests' own settings reads when run as part of the full
    # suite (many unrelated logins started failing with 429s). Monkeypatch
    # reverts the attribute afterward, same as it would an env var.
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    user = await make_user(db_session, email="ratelimit-login@example.com")
    last_response = None
    for _ in range(7):
        last_response = await client.post(
            "/api/auth/login", json={"email": user.email, "password": "wrong-password"}
        )
    assert last_response is not None
    assert last_response.status_code == 429
    assert last_response.json()["code"] == "rate_limited"
    assert "Retry-After" in last_response.headers


async def test_token_create_rate_limit_triggers_429(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    user = await make_user(db_session, email="ratelimit-tokencreate@example.com")
    headers = await _login(client, user.email)
    last_response = None
    for i in range(21):
        last_response = await client.post(
            "/api/auth/tokens", json={"name": f"rl-token-{i}"}, headers=headers
        )
    assert last_response is not None
    assert last_response.status_code == 429


async def test_password_change_rate_limit_triggers_429(
    client: httpx.AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    user = await make_user(db_session, email="ratelimit-pwchange@example.com")
    headers = await _login(client, user.email)
    last_response = None
    for _ in range(6):
        last_response = await client.post(
            "/api/auth/password",
            json={"current_password": "wrong", "new_password": "a-decent-password-1"},
            headers=headers,
        )
    assert last_response is not None
    assert last_response.status_code == 429
