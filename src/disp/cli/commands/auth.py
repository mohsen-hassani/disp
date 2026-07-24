import socket
from typing import Annotated

import typer
from rich.table import Table

from disp.cli import config as cli_config
from disp.cli import render
from disp.cli.client import ApiClient, ClientConfig, CliError, NetworkError
from disp.cli.errors import handle_cli_errors
from disp.cli.state import CliState, build_client, effective_json

MAX_TOKEN_NAME_LEN = 64
MAX_TOKEN_NAME_ATTEMPTS = 9


@handle_cli_errors
def login(
    ctx: typer.Context,
    server: Annotated[str | None, typer.Option("--server", help="Server URL")] = None,
    profile: Annotated[str | None, typer.Option("--profile", help="Profile name")] = None,
) -> None:
    """Log in with email and password; stores a personal access token."""
    state: CliState = ctx.obj
    profile_name = profile or state.profile

    existing = cli_config.get_profile(profile_name)
    server_url = server or state.server_override or (existing or {}).get("server")
    if not server_url:
        server_url = typer.prompt("Server URL")
    server_url = server_url.rstrip("/")

    email = typer.prompt("Email")
    password = typer.prompt("Password", hide_input=True)

    with ApiClient(ClientConfig(server=server_url, token=None, verbose=state.verbose)) as client:
        response = client.request(
            "POST", "/api/auth/login", json={"email": email, "password": password}
        )
        body = response.json()
        access_token = body["access_token"]
        display_name = body["user"]["display_name"]

        pat = _create_cli_token(client, access_token)

    # The password and the access token are discarded here; only the PAT,
    # server, and email are ever persisted (§19.1).
    cli_config.set_profile(profile_name, server=server_url, token=pat, email=email)

    render.out().print(f"Logged in as {display_name} {email}")
    render.out().print(f"Token: {pat[:17]}…")


def _create_cli_token(client: ApiClient, access_token: str) -> str:
    base_name = f"cli@{socket.gethostname()}"[:MAX_TOKEN_NAME_LEN]
    name = base_name
    for attempt in range(1, MAX_TOKEN_NAME_ATTEMPTS + 1):
        if attempt > 1:
            suffix = f"-{attempt}"
            name = base_name[: MAX_TOKEN_NAME_LEN - len(suffix)] + suffix

        response = client.request(
            "POST",
            "/api/auth/tokens",
            json={"name": name, "expires_in_days": None},
            headers={"Authorization": f"Bearer {access_token}"},
            raise_for_status=False,
        )
        if response.status_code == 201:
            token: str = response.json()["token"]
            return token
        if response.status_code == 409:
            continue
        client.raise_for_status(response)

    raise CliError(
        f"Could not create a CLI token after {MAX_TOKEN_NAME_ATTEMPTS} attempts.", exit_code=1
    )


@handle_cli_errors
def logout(
    ctx: typer.Context,
    profile: Annotated[str | None, typer.Option("--profile", help="Profile name")] = None,
) -> None:
    """Revoke the stored token (if reachable) and remove the local profile."""
    state: CliState = ctx.obj
    profile_name = profile or state.profile
    profile_data = cli_config.get_profile(profile_name)

    if profile_data and profile_data.get("token"):
        try:
            _revoke_stored_token(state, profile_data)
        except NetworkError:
            render.err().print(
                "[yellow]Warning: server unreachable — the token was not revoked remotely.[/yellow]"
            )
        except CliError as exc:
            render.err().print(f"[yellow]Warning: could not revoke token remotely: {exc}[/yellow]")

    cli_config.remove_profile(profile_name)
    render.out().print(f"Logged out of profile {profile_name!r}.")


def _revoke_stored_token(state: CliState, profile_data: dict[str, str]) -> None:
    server = state.server_override or profile_data["server"]
    token = profile_data["token"]
    with ApiClient(ClientConfig(server=server, token=token, verbose=state.verbose)) as client:
        response = client.request("GET", "/api/auth/tokens")
        candidates = [t for t in response.json() if token.startswith(t["token_prefix"])]
        if not candidates:
            return
        client.request("DELETE", f"/api/auth/tokens/{candidates[0]['id']}")


@handle_cli_errors
def whoami(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """Print the caller's identity."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        response = client.request("GET", "/api/auth/me")
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
        return

    render.out().print(f"Display name: {data['display_name']}")
    render.out().print(f"Email:        {data['email']}")
    render.out().print(f"Admin:        {data['is_admin']}")
    render.out().print(f"Auth method:  {data['auth_method']}")


tokens_app = typer.Typer(add_completion=False, help="Manage personal access tokens.")


@tokens_app.command("list")
@handle_cli_errors
def tokens_list(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """List the caller's non-revoked tokens."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        response = client.request("GET", "/api/auth/tokens")
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
        return

    table = Table()
    table.add_column("Id")
    table.add_column("Name")
    table.add_column("Prefix")
    table.add_column("Created")
    table.add_column("Last used")
    table.add_column("Expires")
    for token in data:
        table.add_row(
            token["id"][:8],
            token["name"],
            token["token_prefix"],
            token["created_at"],
            token["last_used_at"] or "never",
            token["expires_at"] or "never",
        )
    render.out().print(table)


@tokens_app.command("revoke")
@handle_cli_errors
def tokens_revoke(
    ctx: typer.Context,
    token_id: Annotated[str, typer.Argument(help="Token id")],
) -> None:
    """Revoke a personal access token."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        client.request("DELETE", f"/api/auth/tokens/{token_id}")
    render.out().print(f"Revoked token {token_id}.")


@tokens_app.command("create")
@handle_cli_errors
def tokens_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Token name")],
    expires_days: Annotated[
        int | None, typer.Option("--expires-days", help="Expiry in days")
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """Create a personal access token. The plaintext is shown once."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        response = client.request(
            "POST", "/api/auth/tokens", json={"name": name, "expires_in_days": expires_days}
        )
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
        return

    render.out().print(f"Token: {data['token']}")
    render.err().print("[yellow]This token will not be shown again.[/yellow]")
