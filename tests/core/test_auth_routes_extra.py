import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import DEFAULT_PASSWORD, make_pat, make_user


async def _login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_list_and_delete_pending_invites(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await make_user(db_session, email="admin-invitelist@example.com", is_admin=True)
    headers = await _login(client, admin.email)

    create = await client.post(
        "/api/auth/invites",
        json={"email": "pending-invitee@example.com", "is_admin": False},
        headers=headers,
    )
    invite_id = create.json()["id"]

    listing = await client.get("/api/auth/invites", headers=headers)
    assert listing.status_code == 200
    assert any(i["id"] == invite_id for i in listing.json())

    delete = await client.delete(f"/api/auth/invites/{invite_id}", headers=headers)
    assert delete.status_code == 204

    listing_after = await client.get("/api/auth/invites", headers=headers)
    assert not any(i["id"] == invite_id for i in listing_after.json())


async def test_delete_unknown_invite_returns_404(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    import uuid

    admin = await make_user(db_session, email="admin-invite404@example.com", is_admin=True)
    headers = await _login(client, admin.email)

    response = await client.delete(f"/api/auth/invites/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "core.auth.invite_not_found"


async def test_non_admin_cannot_list_or_delete_invites(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    import uuid

    user = await make_user(db_session, email="nonadmin-invites@example.com")
    headers = await _login(client, user.email)

    listing = await client.get("/api/auth/invites", headers=headers)
    assert listing.status_code == 403

    delete = await client.delete(f"/api/auth/invites/{uuid.uuid4()}", headers=headers)
    assert delete.status_code == 403


async def test_pat_used_where_admin_required_is_still_checked(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await make_user(db_session, email="admin-pat@example.com", is_admin=True)
    _, plaintext = await make_pat(db_session, user_id=admin.id)

    response = await client.get(
        "/api/auth/invites", headers={"Authorization": f"Bearer {plaintext}"}
    )
    assert response.status_code == 200
