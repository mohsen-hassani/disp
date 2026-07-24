import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.dependencies import optional_user
from disp.core.auth.tokens import JWT_ALGORITHM, create_access_token
from disp.core.config import get_settings
from tests.factories import make_pat, make_user


async def test_pat_for_disabled_user_returns_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="deps-pat-disabled@example.com", is_active=True)
    _, plaintext = await make_pat(db_session, user_id=user.id)
    user.is_active = False
    await db_session.flush()

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})

    assert response.status_code == 403
    assert response.json()["code"] == "auth.account_disabled"


async def test_access_token_with_expired_exp_returns_401(client: httpx.AsyncClient) -> None:
    settings = get_settings()
    token = create_access_token(
        user_id=uuid.uuid4(),
        email="x@example.com",
        is_admin=False,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=-60,
    )

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "auth.token_expired"


async def test_access_token_with_non_uuid_sub_returns_401(client: httpx.AsyncClient) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": "not-a-uuid",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": str(uuid.uuid4()),
        "typ": "access",
        "email": "x@example.com",
        "adm": False,
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"


async def test_access_token_for_nonexistent_user_returns_401(client: httpx.AsyncClient) -> None:
    settings = get_settings()
    token = create_access_token(
        user_id=uuid.uuid4(),
        email="ghost@example.com",
        is_admin=False,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=900,
    )

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"


async def test_access_token_for_disabled_user_returns_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="deps-jwt-disabled@example.com")
    await db_session.flush()
    settings = get_settings()
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=900,
    )
    user.is_active = False
    await db_session.flush()

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["code"] == "auth.account_disabled"


async def test_optional_user_returns_none_without_header(db_session: AsyncSession) -> None:
    class _FakeRequest:
        state = type("S", (), {})()

    result = await optional_user(_FakeRequest(), db_session, None)  # type: ignore[arg-type]
    assert result is None


async def test_optional_user_resolves_with_header(db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="deps-optional@example.com")
    await db_session.flush()
    settings = get_settings()
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=900,
    )

    class _FakeRequest:
        state = type("S", (), {})()

    result = await optional_user(_FakeRequest(), db_session, f"Bearer {token}")  # type: ignore[arg-type]
    assert result is not None
    assert result.email == user.email
