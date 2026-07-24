import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import DEFAULT_PASSWORD, make_user


async def _authed(client: httpx.AsyncClient, db_session: AsyncSession, email: str) -> None:
    await make_user(db_session, email=email)
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": DEFAULT_PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"


# WEB-SPEC §3 amendment A1: the manifest's settings panels must carry a JSON
# Schema, not just key/title/description/scope.


async def test_manifest_includes_notes_module_with_no_settings_panels(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _authed(client, db_session, "manifest-notes@example.com")

    response = await client.get("/api/dashboard/manifest")

    assert response.status_code == 200
    modules = {m["domain"]: m for m in response.json()["modules"]}
    assert "notes" in modules
    assert modules["notes"]["settings_panels"] == []


async def test_manifest_surfaces_core_registered_settings_panel(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """core.notifier is registered via Registry.register_core_settings_panel, not
    through any discovered module's manifest — it must still show up under a
    synthetic "core" module entry, or the client's /settings index has nothing
    to list for it despite GET/PUT /api/settings/core already working."""
    await _authed(client, db_session, "manifest-core@example.com")

    response = await client.get("/api/dashboard/manifest")

    assert response.status_code == 200
    modules = {m["domain"]: m for m in response.json()["modules"]}
    assert "core" in modules
    panels = {p["key"]: p for p in modules["core"]["settings_panels"]}
    assert "core.notifier" in panels


async def test_manifest_panel_schema_marks_secret_field_and_keeps_refs_local(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    """WEB-SPEC §3 amendment A2: a secret field's json_schema_extra must reach
    the client as "x-secret": true. Also assert model_json_schema() didn't
    leak an unresolvable $ref — NotifierSettingsSchema.channels is
    list[ChannelConfig], which Pydantic represents as a $ref into a top-level
    $defs block; that $defs block must live inside this same panel's own
    schema document (WEB-SPEC's client has no cross-document $ref resolver)."""
    await _authed(client, db_session, "manifest-secret@example.com")

    response = await client.get("/api/dashboard/manifest")

    modules = {m["domain"]: m for m in response.json()["modules"]}
    panel = next(p for p in modules["core"]["settings_panels"] if p["key"] == "core.notifier")
    schema = panel["schema"]

    properties = schema["properties"]
    assert properties["urls"].get("x-secret") is True
    assert "secret" not in properties["urls"]
    assert properties["channels"].get("x-secret") is None

    # channels: list[ChannelConfig] should resolve through a local $defs block.
    channels_items = properties["channels"]["items"]
    if "$ref" in channels_items:
        ref = channels_items["$ref"]
        assert ref.startswith("#/$defs/")
        def_name = ref.removeprefix("#/$defs/")
        assert "$defs" in schema
        assert def_name in schema["$defs"]
