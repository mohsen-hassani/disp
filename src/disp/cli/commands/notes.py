import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from disp.cli import render
from disp.cli.client import ApiClient, NotFoundError
from disp.cli.errors import handle_cli_errors
from disp.cli.state import CliState, build_client, effective_json

notes_app = typer.Typer(add_completion=False, help="Manage notes.")

PREVIEW_LEN = 60
MIN_PREFIX_LEN = 4


def _preview(body: str) -> str:
    if len(body) <= PREVIEW_LEN:
        return body
    return body[:PREVIEW_LEN] + "…"


def _edit_in_editor(initial_content: str) -> str:
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(initial_content)
        path = Path(f.name)
    try:
        subprocess.run([editor, str(path)], check=True)  # noqa: S603
        return path.read_text()
    finally:
        path.unlink(missing_ok=True)


def _fetch_all_notes(
    client: ApiClient,
    *,
    limit: int = 100,
    pinned: bool | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {"limit": limit}
        if pinned is not None:
            params["pinned"] = pinned
        if q:
            params["q"] = q
        if cursor:
            params["cursor"] = cursor
        response = client.request("GET", "/api/notes", params=params)
        body = response.json()
        items.extend(body["items"])
        if not body["has_more"]:
            break
        cursor = body["next_cursor"]
    return items


def resolve_note_id(client: ApiClient, id_or_prefix: str) -> str:
    try:
        return str(uuid.UUID(id_or_prefix))
    except ValueError:
        pass

    if len(id_or_prefix) < MIN_PREFIX_LEN:
        render.err().print(
            f"[red]Note id {id_or_prefix!r} is too short "
            f"(minimum {MIN_PREFIX_LEN} characters).[/red]"
        )
        raise typer.Exit(code=1)

    candidates = [n for n in _fetch_all_notes(client) if n["id"].startswith(id_or_prefix)]
    if not candidates:
        raise NotFoundError(f"No note found matching id prefix {id_or_prefix!r}.")
    if len(candidates) > 1:
        render.err().print(f"[yellow]Ambiguous id prefix {id_or_prefix!r}; candidates:[/yellow]")
        for candidate in candidates:
            render.err().print(f"  {candidate['id']}")
        raise typer.Exit(code=1)
    return str(candidates[0]["id"])


@notes_app.command("list")
@handle_cli_errors
def notes_list(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
    pinned: Annotated[bool | None, typer.Option("--pinned/--no-pinned")] = None,
    q: Annotated[str | None, typer.Option("-q", "--query")] = None,
    all_pages: Annotated[bool, typer.Option("--all", help="Page through every cursor")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """List the caller's notes."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        if all_pages:
            items = _fetch_all_notes(client, limit=limit, pinned=pinned, q=q)
        else:
            params: dict[str, Any] = {"limit": limit}
            if pinned is not None:
                params["pinned"] = pinned
            if q:
                params["q"] = q
            response = client.request("GET", "/api/notes", params=params)
            items = response.json()["items"]

    if effective_json(state, json_output):
        # §25 item 27 requires `disp notes list --json | jq '.items[0].id'`
        # to work, so the CLI mirrors the API's `{"items": [...]}` envelope
        # rather than emitting a bare array.
        render.emit_json({"items": items})
        return

    table = Table()
    table.add_column("Id")
    table.add_column("Pinned")
    table.add_column("Title")
    table.add_column("Created")
    table.add_column("Preview")
    for note in items:
        created = datetime.fromisoformat(note["created_at"])
        table.add_row(
            note["id"][:8],
            "📌" if note["pinned"] else "",
            note["title"] or "",
            render.humanize_relative(created),
            _preview(note["body"]),
        )
    render.out().print(table)


@notes_app.command("add")
@handle_cli_errors
def notes_add(
    ctx: typer.Context,
    body: Annotated[str | None, typer.Argument()] = None,
    title: Annotated[str | None, typer.Option("--title")] = None,
    pin: Annotated[bool, typer.Option("--pin")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """Create a note. Reads from stdin when piped, or opens $EDITOR."""
    state: CliState = ctx.obj

    if body is None:
        body = _edit_in_editor("") if sys.stdin.isatty() else sys.stdin.read()

    body = body.strip()
    if not body:
        render.err().print("[red]Note body must not be empty.[/red]")
        raise typer.Exit(code=1)

    payload: dict[str, Any] = {"body": body, "pinned": pin}
    if title:
        payload["title"] = title

    with build_client(state) as client:
        response = client.request("POST", "/api/notes", json=payload)
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
    else:
        render.out().print(data["id"])


@notes_app.command("show")
@handle_cli_errors
def notes_show(
    ctx: typer.Context,
    note_id: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """Show a single note. Accepts a full id or an unambiguous prefix."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        full_id = resolve_note_id(client, note_id)
        response = client.request("GET", f"/api/notes/{full_id}")
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
        return

    render.out().print(f"Id:      {data['id']}")
    render.out().print(f"Title:   {data['title'] or '(none)'}")
    render.out().print(f"Pinned:  {data['pinned']}")
    render.out().print(f"Created: {data['created_at']}")
    render.out().print(f"Updated: {data['updated_at']}")
    render.out().print("")
    render.out().print(data["body"])


@notes_app.command("edit")
@handle_cli_errors
def notes_edit(
    ctx: typer.Context,
    note_id: Annotated[str, typer.Argument()],
    title: Annotated[str | None, typer.Option("--title")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    pin: Annotated[bool | None, typer.Option("--pin/--unpin")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw JSON")] = False,
) -> None:
    """Edit a note. With no flags, opens $EDITOR pre-filled with the current body."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        full_id = resolve_note_id(client, note_id)

        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if pin is not None:
            payload["pinned"] = pin

        if body is not None:
            payload["body"] = body
        elif not payload:
            current = client.request("GET", f"/api/notes/{full_id}").json()
            edited = _edit_in_editor(current["body"])
            if edited.strip() == current["body"].strip():
                render.out().print("No changes made.")
                return
            payload["body"] = edited

        response = client.request("PATCH", f"/api/notes/{full_id}", json=payload)
    data = response.json()

    if effective_json(state, json_output):
        render.emit_json(data)
    else:
        render.out().print(f"Updated note {data['id']}.")


@notes_app.command("rm")
@handle_cli_errors
def notes_rm(
    ctx: typer.Context,
    note_id: Annotated[str, typer.Argument()],
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
) -> None:
    """Soft-delete a note."""
    state: CliState = ctx.obj
    with build_client(state) as client:
        full_id = resolve_note_id(client, note_id)
        if not yes and not typer.confirm(f"Delete note {full_id[:8]}?"):
            raise typer.Exit(code=0)
        client.request("DELETE", f"/api/notes/{full_id}")
    render.out().print(f"Deleted note {full_id}.")


@notes_app.command("share")
@handle_cli_errors
def notes_share(
    ctx: typer.Context,
    note_id: Annotated[str, typer.Argument()],
    email: Annotated[str, typer.Option("--email")],
    permission: Annotated[str, typer.Option("--permission")],
) -> None:
    """Grant another user access to a note."""
    if permission not in ("read", "write"):
        render.err().print("[red]--permission must be 'read' or 'write'.[/red]")
        raise typer.Exit(code=2)

    state: CliState = ctx.obj
    with build_client(state) as client:
        full_id = resolve_note_id(client, note_id)
        client.request(
            "POST",
            f"/api/notes/{full_id}/share",
            json={"email": email, "permission": permission},
        )
    render.out().print(f"Shared note {full_id} with {email} ({permission}).")
