import json
import re

from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from disp.cli import config as cli_config
from disp.cli.main import app as cli_app
from tests.factories import make_pat, make_user

runner = CliRunner()
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


async def _seeded_profile(cli_db: AsyncSession, cli_env: str, *, email: str) -> str:
    user = await make_user(cli_db, email=email)
    _, plaintext = await make_pat(cli_db, user_id=user.id)
    await cli_db.commit()
    cli_config.set_profile("default", server=cli_env, token=plaintext, email=email)
    return str(user.id)


async def test_whoami_plain_and_json(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-whoami@example.com")

    plain = runner.invoke(cli_app, ["whoami"])
    assert plain.exit_code == 0, plain.output
    assert "cmd-whoami@example.com" in plain.output

    as_json = runner.invoke(cli_app, ["whoami", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = json.loads(as_json.output)
    assert body["email"] == "cmd-whoami@example.com"
    assert body["auth_method"] == "api_token"


async def test_tokens_list_and_revoke(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-tokens@example.com")

    list_plain = runner.invoke(cli_app, ["tokens", "list"])
    assert list_plain.exit_code == 0, list_plain.output

    list_json = runner.invoke(cli_app, ["tokens", "list", "--json"])
    assert list_json.exit_code == 0, list_json.output
    tokens = json.loads(list_json.output)
    assert len(tokens) == 1  # the seeded PAT itself

    # Revoking the profile's own active token is unusual but valid to
    # exercise: the very next request correctly fails auth (401 -> exit 3),
    # since that token is now the one that just got revoked.
    revoke = runner.invoke(cli_app, ["tokens", "revoke", tokens[0]["id"]])
    assert revoke.exit_code == 0, revoke.output
    assert "Revoked" in revoke.output

    list_after = runner.invoke(cli_app, ["tokens", "list"])
    assert list_after.exit_code == 3, list_after.output


async def test_tokens_create_from_a_pat_profile_is_forbidden(
    cli_env: str, cli_db: AsyncSession
) -> None:
    # S7/§10: a PAT cannot mint another PAT. Every profile the real `disp
    # login` flow ever writes holds a PAT, so this 403 is the CLI's actual,
    # everyday behavior for `tokens create` — not just an edge case.
    await _seeded_profile(cli_db, cli_env, email="cmd-tokens-create-pat@example.com")

    result = runner.invoke(cli_app, ["tokens", "create", "nope"])

    assert result.exit_code == 1, result.output  # CliPermissionError -> exit 1
    assert "cannot be used to create" in result.output


async def test_tokens_create_succeeds_from_an_access_token_profile(
    cli_env: str, cli_db: AsyncSession
) -> None:
    # `disp login` only ever persists a PAT, so `tokens create`'s success
    # path (auth_method == "access_token") is unreachable through ordinary
    # CLI usage. Exercised here by writing a real JWT access token directly
    # into the profile — a config shape `disp login` never produces itself,
    # but one the server legitimately accepts (nothing but the token's own
    # shape distinguishes a PAT from an access token to the API).
    from disp.core.auth.tokens import create_access_token
    from disp.core.config import get_settings

    user = await make_user(cli_db, email="cmd-tokens-create-jwt@example.com")
    await cli_db.commit()
    settings = get_settings()
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    cli_config.set_profile("default", server=cli_env, token=access_token, email=user.email)

    create_plain = runner.invoke(cli_app, ["tokens", "create", "minted-token"])
    assert create_plain.exit_code == 0, create_plain.output
    assert "will not be shown again" in create_plain.output

    create_json = runner.invoke(cli_app, ["tokens", "create", "minted-token-2", "--json"])
    assert create_json.exit_code == 0, create_json.output
    created = json.loads(create_json.output)
    assert created["token"].startswith("disp_pat_")


async def test_logout_revokes_and_removes_profile(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-logout@example.com")

    result = runner.invoke(cli_app, ["logout"])
    assert result.exit_code == 0, result.output
    assert "Logged out" in result.output
    assert cli_config.get_profile("default") is None


async def test_dashboard_plain_and_json(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-dashboard@example.com")

    plain = runner.invoke(cli_app, ["dashboard"])
    assert plain.exit_code == 0, plain.output

    as_json = runner.invoke(cli_app, ["dashboard", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = json.loads(as_json.output)
    assert "tiles" in body


async def test_modules_plain_and_json(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-modules@example.com")

    plain = runner.invoke(cli_app, ["modules"])
    assert plain.exit_code == 0, plain.output
    assert "notes" in plain.output

    as_json = runner.invoke(cli_app, ["modules", "--json"])
    assert as_json.exit_code == 0, as_json.output
    body = json.loads(as_json.output)
    domains = {m["domain"] for m in body["modules"]}
    # "core" is a synthetic entry surfacing core-registered settings panels
    # (e.g. core.notifier) that belong to no discovered module — see
    # dashboard.py's get_manifest().
    assert domains == {"notes", "core"}


async def test_health_plain_output(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-health@example.com")

    result = runner.invoke(cli_app, ["health"])
    assert result.exit_code == 0, result.output
    assert "Status:" in result.output


async def test_notes_show_edit_rm_share_plain(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-notes-owner@example.com")
    grantee_email = "cmd-notes-grantee@example.com"
    await make_user(cli_db, email=grantee_email)
    await cli_db.commit()

    add_result = runner.invoke(cli_app, ["notes", "add", "hello from cmd test", "--title", "T"])
    assert add_result.exit_code == 0, add_result.output
    note_id = ANSI_ESCAPE_RE.sub("", add_result.output).strip()

    show_plain = runner.invoke(cli_app, ["notes", "show", note_id])
    assert show_plain.exit_code == 0, show_plain.output
    assert "hello from cmd test" in show_plain.output

    edit_result = runner.invoke(cli_app, ["notes", "edit", note_id, "--title", "Updated"])
    assert edit_result.exit_code == 0, edit_result.output
    assert "Updated note" in edit_result.output

    edit_json = runner.invoke(cli_app, ["notes", "edit", note_id, "--pin", "--json"])
    assert edit_json.exit_code == 0, edit_json.output
    assert json.loads(edit_json.output)["pinned"] is True

    share_result = runner.invoke(
        cli_app,
        ["notes", "share", note_id, "--email", grantee_email, "--permission", "read"],
    )
    assert share_result.exit_code == 0, share_result.output
    assert "Shared note" in share_result.output

    rm_result = runner.invoke(cli_app, ["notes", "rm", note_id, "--yes"])
    assert rm_result.exit_code == 0, rm_result.output
    assert "Deleted note" in rm_result.output

    show_after_delete = runner.invoke(cli_app, ["notes", "show", note_id])
    assert show_after_delete.exit_code == 6, show_after_delete.output


async def test_notes_list_pinned_filter_and_query(cli_env: str, cli_db: AsyncSession) -> None:
    await _seeded_profile(cli_db, cli_env, email="cmd-notes-filter@example.com")

    runner.invoke(cli_app, ["notes", "add", "alpha searchable note"])
    runner.invoke(cli_app, ["notes", "add", "beta note", "--pin"])

    pinned_only = runner.invoke(cli_app, ["notes", "list", "--pinned", "--json"])
    assert pinned_only.exit_code == 0, pinned_only.output
    items = json.loads(pinned_only.output)["items"]
    assert all(item["pinned"] for item in items)
    assert len(items) == 1

    query_result = runner.invoke(cli_app, ["notes", "list", "-q", "alpha", "--json"])
    assert query_result.exit_code == 0, query_result.output
    query_items = json.loads(query_result.output)["items"]
    assert any("alpha" in item["body"] for item in query_items)

    all_pages = runner.invoke(cli_app, ["notes", "list", "--all", "--json"])
    assert all_pages.exit_code == 0, all_pages.output
    assert len(json.loads(all_pages.output)["items"]) == 2
