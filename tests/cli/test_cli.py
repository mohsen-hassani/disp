import json
import re
import stat
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from typer.testing import CliRunner

from disp.cli import config as cli_config
from disp.cli.main import app as cli_app
from tests.factories import DEFAULT_PASSWORD, make_pat, make_user

runner = CliRunner()

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


async def _seeded_profile(cli_db: AsyncSession, cli_env: str, *, email: str) -> str:
    user = await make_user(cli_db, email=email)
    _, plaintext = await make_pat(cli_db, user_id=user.id)
    await cli_db.commit()
    cli_config.set_profile("default", server=cli_env, token=plaintext, email=email)
    return str(user.id)


# Case 57: `disp login` writes a 0600 config containing a PAT and no password.


async def test_login_writes_0600_config_with_pat_and_no_password(
    cli_env: str, cli_db: AsyncSession, tmp_path: Path
) -> None:
    await make_user(cli_db, email="cli-login@example.com")
    await cli_db.commit()

    result = runner.invoke(
        cli_app,
        ["login", "--server", cli_env],
        input=f"cli-login@example.com\n{DEFAULT_PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output

    config_file = cli_config.config_path()
    mode = stat.S_IMODE(config_file.stat().st_mode)
    assert mode == 0o600

    raw = config_file.read_text()
    assert "disp_pat_" in raw
    assert DEFAULT_PASSWORD not in raw

    data = cli_config.load_config()
    profile = data["profiles"]["default"]
    assert profile["token"].startswith("disp_pat_")
    assert profile["email"] == "cli-login@example.com"
    assert "password" not in profile


# Case 58: a config file with mode 0644 is refused with exit 3.


async def test_group_readable_config_refused_with_exit_3(
    cli_env: str, cli_db: AsyncSession, tmp_path: Path
) -> None:
    await _seeded_profile(cli_db, cli_env, email="cli-perm@example.com")
    cli_config.config_path().chmod(0o644)

    result = runner.invoke(cli_app, ["health"])

    plain_output = ANSI_ESCAPE_RE.sub("", result.output).replace("\n", " ")
    assert result.exit_code == 3, result.output
    assert "chmod" in plain_output
    assert "600" in plain_output


# Case 59: `disp notes add` from piped stdin creates a note.


async def test_notes_add_from_piped_stdin_creates_note(
    cli_env: str, cli_db: AsyncSession, tmp_path: Path
) -> None:
    await _seeded_profile(cli_db, cli_env, email="cli-stdin@example.com")

    result = runner.invoke(cli_app, ["notes", "add"], input="a note piped from stdin\n")

    assert result.exit_code == 0, result.output
    note_id = result.output.strip()
    assert note_id

    show_result = runner.invoke(cli_app, ["notes", "show", note_id, "--json"])
    assert show_result.exit_code == 0, show_result.output
    body = json.loads(show_result.output)
    assert body["body"] == "a note piped from stdin"


# Case 60: --json output parses as JSON and contains no ANSI escapes.


async def test_json_output_parses_and_has_no_ansi_escapes(
    cli_env: str, cli_db: AsyncSession, tmp_path: Path
) -> None:
    await _seeded_profile(cli_db, cli_env, email="cli-json@example.com")

    result = runner.invoke(cli_app, ["notes", "list", "--json"])

    assert result.exit_code == 0, result.output
    assert ANSI_ESCAPE_RE.search(result.output) is None
    parsed = json.loads(result.output)
    assert "items" in parsed


# Case 61: a 401 from the server exits 3 with a "run `disp login`" message.


async def test_401_exits_3_with_run_login_message(
    cli_env: str, cli_db: AsyncSession, tmp_path: Path
) -> None:
    user = await make_user(cli_db, email="cli-401@example.com")
    _, plaintext = await make_pat(cli_db, user_id=user.id)
    await cli_db.commit()
    cli_config.set_profile(
        "default", server=cli_env, token=plaintext + "corrupted", email=user.email
    )

    # /health is a public endpoint (no auth dependency) — a bad token never
    # matters there, so exercise an endpoint that actually requires auth.
    result = runner.invoke(cli_app, ["whoami"])

    assert result.exit_code == 3, result.output
    assert "disp login" in result.output
