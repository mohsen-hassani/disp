from typing import Annotated, Any

import typer
from rich.panel import Panel

from disp.cli import render
from disp.cli.errors import handle_cli_errors
from disp.cli.state import CliState, build_client, effective_json

MAX_ITEMS_SHOWN = 5


@handle_cli_errors
def dashboard(
    ctx: typer.Context,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """Render every registered dashboard tile."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        response = client.request("GET", "/api/dashboard/tiles")
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
        return

    for tile in data["tiles"]:
        render.out().print(_render_tile_panel(tile))


def _render_tile_panel(tile: dict[str, Any]) -> Panel:
    lines: list[str] = []
    if tile.get("count") is not None:
        lines.append(f"[bold]{tile['count']}[/bold]")

    items = tile.get("items", [])[:MAX_ITEMS_SHOWN]
    if items:
        for item in items:
            marker = ""
            if item.get("done") is True:
                marker = "[green]✓[/green] "
            elif item.get("done") is False:
                marker = "[dim]○[/dim] "
            secondary = f" [dim]({item['secondary']})[/dim]" if item.get("secondary") else ""
            lines.append(f"{marker}{item['primary']}{secondary}")
    else:
        lines.append(f"[dim]{tile['empty_text']}[/dim]")

    if tile.get("actions"):
        action_labels = ", ".join(action["label"] for action in tile["actions"])
        lines.append(f"[dim]Actions: {action_labels}[/dim]")

    return Panel("\n".join(lines), title=tile["title"])
