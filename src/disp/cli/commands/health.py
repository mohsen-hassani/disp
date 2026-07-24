from typing import Annotated

import typer

from disp.cli import render
from disp.cli.errors import handle_cli_errors
from disp.cli.state import CliState, build_client, effective_json


@handle_cli_errors
def health(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """Check the server's health."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        response = client.request("GET", "/health")
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
    else:
        table_lines = [
            f"Status:           {data['status']}",
            f"Version:          {data['version']}",
            f"Database:         {data['database']}",
            f"Modules:          {', '.join(data['modules']) or '(none)'}",
            f"Worker last seen: {data['worker_last_seen'] or 'never'}",
        ]
        render.out().print("\n".join(table_lines))

    if data["status"] != "ok":
        raise typer.Exit(code=1)
