from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.auth.tokens import hash_refresh_token
from disp.core.models import Session as SessionModel
from disp.core.models import User
from tests.factories import DEFAULT_PASSWORD, make_invite, make_pat, make_session_row, make_user

CSRF_HEADERS = {"X-Requested-With": "disp"}


def _login_payload(email: str, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
    return {"email": email, "password": password}


# Case 3: login succeeds and sets a cookie with the correct attributes.


async def test_login_succeeds_and_sets_refresh_cookie(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="login@example.com")

    response = await client.post("/api/auth/login", json=_login_payload("login@example.com"))

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "login@example.com"

    set_cookie = response.headers.get("set-cookie", "")
    assert "disp_refresh=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/api/auth" in set_cookie


# Case 4: unknown email and wrong password return byte-identical bodies (modulo
# request_id) and both 401.


async def test_unknown_email_and_wrong_password_are_indistinguishable(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="real@example.com")

    unknown_response = await client.post(
        "/api/auth/login", json=_login_payload("nobody@example.com")
    )
    wrong_password = "totally-wrong-pw"  # noqa: S105
    wrong_password_response = await client.post(
        "/api/auth/login",
        json=_login_payload("real@example.com", password=wrong_password),
    )

    assert unknown_response.status_code == 401
    assert wrong_password_response.status_code == 401

    unknown_body = unknown_response.json()
    wrong_body = wrong_password_response.json()
    unknown_body.pop("request_id", None)
    wrong_body.pop("request_id", None)
    assert unknown_body == wrong_body


# Case 5: login on a disabled account returns 403.


async def test_login_on_disabled_account_returns_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="disabled@example.com", is_active=False)

    response = await client.post("/api/auth/login", json=_login_payload("disabled@example.com"))

    assert response.status_code == 403
    assert response.json()["code"] == "auth.account_disabled"


# Case 6: refresh rotates: new access token issued, new cookie set, old refresh
# token now rejected.


async def test_refresh_rotates_token(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await make_user(db_session, email="rotate@example.com")
    login_response = await client.post("/api/auth/login", json=_login_payload("rotate@example.com"))
    old_access_token = login_response.json()["access_token"]

    refresh_response = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
    assert refresh_response.status_code == 200
    new_access_token = refresh_response.json()["access_token"]
    assert new_access_token != old_access_token
    assert "disp_refresh=" in refresh_response.headers.get("set-cookie", "")

    # The client's cookie jar now holds the NEW refresh token; manually
    # presenting the rotated-out cookie must fail. httpx's cookie jar has
    # already replaced it, so build a fresh unauthenticated request with the
    # original cookie captured from the login response.
    old_cookie = login_response.cookies.get("disp_refresh")
    assert old_cookie
    client.cookies.set("disp_refresh", old_cookie)
    replay_response = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
    assert replay_response.status_code == 401


# Case 7: refresh replay of a rotated token returns 401
# auth.refresh_token_reused, and every session in the family has revoked_at set.


async def test_refresh_replay_revokes_family(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="replay@example.com")
    login_response = await client.post("/api/auth/login", json=_login_payload("replay@example.com"))
    original_refresh = login_response.cookies.get("disp_refresh")
    assert original_refresh

    first_refresh = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
    assert first_refresh.status_code == 200

    # Replay the ORIGINAL (now-rotated-out) token: reuse detection fires.
    client.cookies.set("disp_refresh", original_refresh)
    replay_response = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
    assert replay_response.status_code == 401
    assert replay_response.json()["code"] == "auth.refresh_token_reused"

    user_row = (
        await db_session.execute(select(User).where(User.email == "replay@example.com"))
    ).scalar_one()
    sessions = (
        (await db_session.execute(select(SessionModel).where(SessionModel.user_id == user_row.id)))
        .scalars()
        .all()
    )
    assert len(sessions) >= 2
    assert all(s.revoked_at is not None for s in sessions)


# Case 8: refresh without X-Requested-With returns 403.


async def test_refresh_without_csrf_header_returns_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="csrf@example.com")
    await client.post("/api/auth/login", json=_login_payload("csrf@example.com"))

    response = await client.post("/api/auth/refresh")

    assert response.status_code == 403
    assert response.json()["code"] == "auth.csrf_required"


# Case 9: expired refresh token returns 401 auth.refresh_token_expired.


async def test_expired_refresh_token_returns_401(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="expired@example.com")
    raw_token = "expired-refresh-token-value"  # noqa: S105
    await make_session_row(
        db_session,
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(UTC) - timedelta(seconds=10),
    )

    client.cookies.set("disp_refresh", raw_token)
    response = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)

    assert response.status_code == 401
    assert response.json()["code"] == "auth.refresh_token_expired"


# Case 10: logout revokes the family and clears the cookie; a second logout
# still returns 204.


async def test_logout_revokes_family_and_is_idempotent(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="logout@example.com")
    await client.post("/api/auth/login", json=_login_payload("logout@example.com"))

    first_logout = await client.post("/api/auth/logout", headers=CSRF_HEADERS)
    assert first_logout.status_code == 204
    assert 'disp_refresh=""' in first_logout.headers.get("set-cookie", "")

    sessions = (
        (await db_session.execute(select(SessionModel).where(SessionModel.user_id == user.id)))
        .scalars()
        .all()
    )
    assert all(s.revoked_at is not None for s in sessions)

    second_logout = await client.post("/api/auth/logout", headers=CSRF_HEADERS)
    assert second_logout.status_code == 204


# Case 11: PAT creation returns plaintext once; the same value never appears
# in the list response.


async def test_pat_creation_plaintext_never_relisted(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="pat@example.com")
    login_response = await client.post("/api/auth/login", json=_login_payload("pat@example.com"))
    access_token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    create_response = await client.post(
        "/api/auth/tokens", json={"name": "my-token", "expires_in_days": None}, headers=headers
    )
    assert create_response.status_code == 201
    plaintext = create_response.json()["token"]
    assert plaintext.startswith("disp_pat_")

    list_response = await client.get("/api/auth/tokens", headers=headers)
    assert list_response.status_code == 200
    assert plaintext not in list_response.text
    assert "token" not in list_response.json()[0]


# Case 12: a PAT authenticates a normal endpoint successfully.


async def test_pat_authenticates_normal_endpoint(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="patauth@example.com")
    _, plaintext = await make_pat(db_session, user_id=user.id)

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})

    assert response.status_code == 200
    assert response.json()["auth_method"] == "api_token"
    assert response.json()["email"] == "patauth@example.com"


# Case 13: a PAT is rejected by POST /api/auth/tokens with 403 auth.pat_cannot_mint.


async def test_pat_cannot_mint_another_pat(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="patmint@example.com")
    _, plaintext = await make_pat(db_session, user_id=user.id)

    response = await client.post(
        "/api/auth/tokens",
        json={"name": "second-token", "expires_in_days": None},
        headers={"Authorization": f"Bearer {plaintext}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "auth.pat_cannot_mint"


# Case 14: a PAT is rejected by POST /api/auth/password.


async def test_pat_cannot_change_password(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="patpw@example.com")
    _, plaintext = await make_pat(db_session, user_id=user.id)

    response = await client.post(
        "/api/auth/password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "a-new-password-123456"},
        headers={"Authorization": f"Bearer {plaintext}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "auth.pat_insufficient"


# Case 15: a revoked PAT returns 401; an expired PAT returns 401.


async def test_revoked_pat_returns_401(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="revokedpat@example.com")
    _, plaintext = await make_pat(db_session, user_id=user.id, revoked_at=datetime.now(UTC))

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})

    assert response.status_code == 401
    assert response.json()["code"] == "auth.token_revoked"


async def test_expired_pat_returns_401(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="expiredpat@example.com")
    _, plaintext = await make_pat(
        db_session, user_id=user.id, expires_at=datetime.now(UTC) - timedelta(seconds=5)
    )

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})

    assert response.status_code == 401
    assert response.json()["code"] == "auth.token_expired"


# Case 16: last_used_at updates on first use and does not update again within
# 60 seconds.


async def test_pat_last_used_at_updates_on_first_use_only_within_window(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="lastused@example.com")
    token_row, plaintext = await make_pat(db_session, user_id=user.id, last_used_at=None)

    await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})
    await db_session.refresh(token_row)
    first_seen = token_row.last_used_at
    assert first_seen is not None

    await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})
    await db_session.refresh(token_row)
    assert token_row.last_used_at == first_seen

    # Simulate the 60s window having elapsed by backdating last_used_at directly.
    token_row.last_used_at = datetime.now(UTC) - timedelta(seconds=61)
    await db_session.flush()

    await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})
    await db_session.refresh(token_row)
    assert token_row.last_used_at > first_seen


# Case 17: current_user returns an equivalent CurrentUser (excluding
# auth_method) for a JWT and a PAT belonging to the same user.


async def test_jwt_and_pat_resolve_to_equivalent_current_user(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="equiv@example.com")
    _, plaintext = await make_pat(db_session, user_id=user.id)
    login_response = await client.post("/api/auth/login", json=_login_payload("equiv@example.com"))
    access_token = login_response.json()["access_token"]

    via_jwt = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    via_pat = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {plaintext}"})

    jwt_body = via_jwt.json()
    pat_body = via_pat.json()
    assert jwt_body["auth_method"] == "access_token"
    assert pat_body["auth_method"] == "api_token"
    jwt_body.pop("auth_method")
    pat_body.pop("auth_method")
    assert jwt_body == pat_body


# Case 18: missing, malformed, and garbage Authorization headers each return
# the documented 401 code.


async def test_missing_authorization_header(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.missing_credentials"


async def test_malformed_authorization_header(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401
    assert response.json()["code"] == "auth.malformed_credentials"


async def test_garbage_bearer_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage.value"})
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"


# Case 19: invite create -> accept -> login works; the token is single-use
# (second accept returns 409).


async def test_invite_accept_login_flow_and_single_use(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="admin-invite@example.com", is_admin=True)
    admin_login = await client.post(
        "/api/auth/login", json=_login_payload("admin-invite@example.com")
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    create_response = await client.post(
        "/api/auth/invites",
        json={"email": "invitee@example.com", "is_admin": False},
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    invite_token = create_response.json()["token"]

    accepted_password = "a-perfectly-fine-password-1"  # noqa: S105
    accept_response = await client.post(
        "/api/auth/accept-invite",
        json={
            "token": invite_token,
            "display_name": "Invitee",
            "password": accepted_password,
        },
    )
    assert accept_response.status_code == 201
    assert accept_response.json()["user"]["email"] == "invitee@example.com"

    login_response = await client.post(
        "/api/auth/login",
        json=_login_payload("invitee@example.com", password=accepted_password),
    )
    assert login_response.status_code == 200

    second_accept = await client.post(
        "/api/auth/accept-invite",
        json={
            "token": invite_token,
            "display_name": "Invitee Again",
            "password": "another-fine-password-12",
        },
    )
    assert second_accept.status_code == 409
    assert second_accept.json()["code"] == "auth.invite_used"


# Case 20: an expired invite returns 410.


async def test_expired_invite_returns_410(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await make_user(db_session, email="admin-expired@example.com", is_admin=True)

    # accept-invite hashes the presented plaintext to look up the row, so the
    # fixture row's token_hash must be derived from a plaintext we control.
    import hashlib

    plaintext = "known-plaintext-invite-token"
    token_hash = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    await make_invite(
        db_session,
        email="expired-invitee@example.com",
        is_admin=False,
        created_by=admin.id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        token_hash=token_hash,
    )

    response = await client.post(
        "/api/auth/accept-invite",
        json={"token": plaintext, "display_name": "X", "password": "a-decent-password-123"},
    )
    assert response.status_code == 410
    assert response.json()["code"] == "auth.invite_expired"


# Case 21: a second pending invite for the same email returns 409.


async def test_second_pending_invite_same_email_returns_409(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="admin-pending@example.com", is_admin=True)
    admin_login = await client.post(
        "/api/auth/login", json=_login_payload("admin-pending@example.com")
    )
    headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    first = await client.post(
        "/api/auth/invites",
        json={"email": "dup-invitee@example.com", "is_admin": False},
        headers=headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/auth/invites",
        json={"email": "dup-invitee@example.com", "is_admin": False},
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["code"] == "auth.invite_pending"


# Case 22: non-admin invite creation returns 403.


async def test_non_admin_cannot_create_invite(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await make_user(db_session, email="nonadmin@example.com", is_admin=False)
    login_response = await client.post(
        "/api/auth/login", json=_login_payload("nonadmin@example.com")
    )
    headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = await client.post(
        "/api/auth/invites",
        json={"email": "someone@example.com", "is_admin": False},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "auth.admin_required"


# Case 23: password change revokes other sessions but not the caller's.


async def test_password_change_revokes_other_sessions_not_callers(
    client: httpx.AsyncClient, db_session: AsyncSession, app: object
) -> None:
    await make_user(db_session, email="pwchange@example.com")

    # "Other device": a separate client (own cookie jar) hitting the same app.
    other_transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(
        transport=other_transport, base_url="http://testserver"
    ) as other_client:
        other_login = await other_client.post(
            "/api/auth/login", json=_login_payload("pwchange@example.com")
        )
        assert other_login.status_code == 200

        this_login = await client.post(
            "/api/auth/login", json=_login_payload("pwchange@example.com")
        )
        access_token = this_login.json()["access_token"]

        change_response = await client.post(
            "/api/auth/password",
            json={
                "current_password": DEFAULT_PASSWORD,
                "new_password": "a-brand-new-password-123",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert change_response.status_code == 204

        this_refresh = await client.post("/api/auth/refresh", headers=CSRF_HEADERS)
        assert this_refresh.status_code == 200

        other_refresh = await other_client.post("/api/auth/refresh", headers=CSRF_HEADERS)
        assert other_refresh.status_code == 401
