"""`disp-admin translation ...` — the operator-facing surface for the core
translation service (M22-translation.md §10, §12).

§10 deliberately ships no HTTP usage route, unlike M19's
`GET /api/llm/usage`: the character-budget question is operational rather
than product-facing, so it is answered here instead of by adding a router, a
response model and an auth surface to a service that otherwise has none. Add
the HTTP route when a client needs to render it, not before.

No Platform in CLI context, so the command builds its own engine and
session-maker, mirroring seed_admin in cli_admin.py.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

import typer

from disp.core.config import get_settings
from disp.core.db import create_engine, create_session_maker
from disp.core.translation.usage import summarize

translation_app = typer.Typer(add_completion=False, help="Inspect core translation usage.")


@translation_app.command("usage")
def usage(
    days: Annotated[
        int, typer.Option("--days", min=1, help="How many days back to summarise")
    ] = 30,
    backend: Annotated[
        str | None, typer.Option("--backend", help="Only this backend (e.g. deepl)")
    ] = None,
) -> None:
    """Character and call totals from core.translation_call, grouped by
    backend, operation and day.

    `chars` is the number that matters: providers meter source characters,
    and a free tier is a hard monthly ceiling rather than an overage charge.
    """
    asyncio.run(_usage(days=days, backend=backend))


async def _usage(*, days: int, backend: str | None) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_maker = create_session_maker(engine)
    since = datetime.now(UTC) - timedelta(days=days)

    try:
        async with session_maker() as session:
            summary = await summarize(session, since=since, backend=backend)
    finally:
        await engine.dispose()

    if not summary.rows:
        typer.echo(f"No translation calls in the last {days} days.")
        return

    typer.echo(
        f"{'day':<12}{'backend':<10}{'operation':<12}{'outcome':<16}{'calls':>7}{'chars':>10}"
    )
    for row in summary.rows:
        typer.echo(
            f"{row.day.isoformat():<12}{row.backend:<10}{row.operation:<12}"
            f"{row.outcome:<16}{row.call_count:>7}{row.char_count:>10}"
        )
    typer.echo(
        f"\n{summary.total_calls} calls, {summary.total_texts} texts, "
        f"{summary.total_chars} characters over {days} days."
    )
