from typing import Annotated

import typer

from disp import __version__
from disp.cli import config as cli_config
from disp.cli import render
from disp.cli.client import CliError
from disp.cli.commands import auth as auth_commands
from disp.cli.commands import dashboard as dashboard_commands
from disp.cli.commands import health as health_commands
from disp.cli.commands import modules as modules_commands
from disp.cli.commands import notes as notes_commands
from disp.cli.state import CliState

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if value:
        render.out().print(f"disp {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    ctx: typer.Context,
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="Select a profile")] = None,
    server: Annotated[
        str | None, typer.Option("--server", help="Override the server URL for one invocation")
    ] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit raw JSON instead of Rich tables")
    ] = False,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="Disable colour (also honours NO_COLOR)")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Log requests to stderr")
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version", help="Print version and exit", callback=_version_callback, is_eager=True
        ),
    ] = False,
) -> None:
    render.configure(no_color=no_color)
    try:
        resolved_profile = profile or cli_config.default_profile_name()
    except CliError as exc:
        # This runs in the root callback, before any @handle_cli_errors-wrapped
        # command body — a config-file error here (e.g. bad file permissions)
        # would otherwise bypass the §19.3 exit-code mapping entirely and
        # surface as an unhandled exception (Click's default exit code 1).
        render.err().print(f"[red]Error:[/red] {exc.message}")
        raise typer.Exit(code=exc.exit_code) from None
    ctx.obj = CliState(
        profile=resolved_profile,
        server_override=server,
        json_mode=json_output,
        no_color=no_color,
        verbose=verbose,
    )


app.command("login")(auth_commands.login)
app.command("logout")(auth_commands.logout)
app.command("whoami")(auth_commands.whoami)
app.add_typer(auth_commands.tokens_app, name="tokens")

app.command("health")(health_commands.health)
app.command("modules")(modules_commands.list_modules)
app.command("dashboard")(dashboard_commands.dashboard)

app.add_typer(notes_commands.notes_app, name="notes")
