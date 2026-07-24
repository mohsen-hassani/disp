from dataclasses import dataclass

from disp.cli import config as cli_config
from disp.cli.client import ApiClient, AuthError, ClientConfig


@dataclass
class CliState:
    profile: str
    server_override: str | None
    json_mode: bool
    no_color: bool
    verbose: bool


def effective_json(state: CliState, json_flag: bool) -> bool:
    """`--json` is accepted both before the subcommand (root option, stored in
    `state.json_mode`) and after it (each leaf command's own `--json`), since
    Click only recognizes a group's options when they precede the subcommand
    name, but §25's acceptance criteria requires `disp notes list --json`."""
    return json_flag or state.json_mode


def resolve_server(state: CliState, profile_data: dict[str, str] | None) -> str | None:
    if state.server_override:
        return state.server_override
    if profile_data:
        return profile_data.get("server")
    return None


def build_client(state: CliState) -> ApiClient:
    profile_data = cli_config.get_profile(state.profile)
    if not profile_data or not profile_data.get("token"):
        raise AuthError()

    server = resolve_server(state, profile_data)
    if not server:
        raise AuthError("No server configured — run `disp login`")

    return ApiClient(
        ClientConfig(server=server, token=profile_data["token"], verbose=state.verbose)
    )
