from typing import Annotated

import typer
from rich.table import Table

from disp.cli import render
from disp.cli.errors import handle_cli_errors
from disp.cli.state import CliState, build_client, effective_json


@handle_cli_errors
def list_modules(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """List the platform's discovered modules."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        response = client.request("GET", "/api/dashboard/manifest")
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
        return

    table = Table()
    table.add_column("Domain")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Tiles", justify="right")
    table.add_column("Jobs", justify="right")
    for module in data["modules"]:
        table.add_row(
            module["domain"],
            module["name"],
            module["version"],
            str(len(module["tiles"])),
            # §16.1: scheduled_jobs are internal and never exposed by this
            # endpoint, so there is no real count to show here.
            "—",
        )
    render.out().print(table)
