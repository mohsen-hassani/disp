"""`disp-admin files ...` — operational commands for the core file service
(M18-files.md §8.3, docs/operations.md). No Platform in CLI context, so every
command builds its own engine/session-maker, mirroring seed_admin in
cli_admin.py.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

import typer
from sqlalchemy import select

from disp.core.config import get_settings
from disp.core.db import create_engine, create_session_maker
from disp.core.files.store import FileStore
from disp.core.files.sweep import run_sweep
from disp.core.models import FileRecord

files_app = typer.Typer(add_completion=False, help="Manage the core file service.")


@dataclass
class VerifyReport:
    rows_missing_objects: list[tuple[str, str]] = field(default_factory=list)
    objects_missing_rows: list[str] = field(default_factory=list)
    pending_purge: int = 0
    other_buckets: int = 0


@files_app.command("verify")
def verify() -> None:
    """Report rows whose object is missing from the bucket, and bucket objects
    no row references. Deletes nothing (I3) — the first thing to run after a
    database restore."""
    report = asyncio.run(_verify())

    typer.echo(f"Rows with no backing object: {len(report.rows_missing_objects)}")
    for file_id, storage_key in report.rows_missing_objects:
        typer.secho(f"  {file_id}  {storage_key}", fg=typer.colors.YELLOW)
    typer.echo(f"Objects with no row: {len(report.objects_missing_rows)}")
    for key in report.objects_missing_rows:
        typer.secho(f"  {key}", fg=typer.colors.YELLOW)
    if report.pending_purge:
        typer.echo(f"Rows marked deleted, awaiting purge: {report.pending_purge}")
    if report.other_buckets:
        typer.echo(f"Rows in other buckets/backends (not checked): {report.other_buckets}")

    if not report.rows_missing_objects and not report.objects_missing_rows:
        typer.secho(
            "Clean: every row has an object, every object has a row.", fg=typer.colors.GREEN
        )


async def _verify() -> VerifyReport:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_maker = create_session_maker(engine)
    files = FileStore.from_settings(settings, session_maker=session_maker)
    try:
        return await diff_bucket(files)
    finally:
        await engine.dispose()


async def diff_bucket(files: FileStore) -> VerifyReport:
    """Rows vs. one ListObjectsV2 pass over the active bucket's prefix — a
    single listing rather than a HEAD per row (each a billed operation)."""
    backend = files.backend
    report = VerifyReport()
    async with files.open_session() as session:
        result = await session.execute(
            select(
                FileRecord.id,
                FileRecord.backend,
                FileRecord.bucket,
                FileRecord.storage_key,
                FileRecord.deleted_at,
            )
        )
        rows = result.all()

    live: dict[str, str] = {}
    known_keys: set[str] = set()
    for row in rows:
        if row.backend != backend.name or row.bucket != backend.bucket:
            report.other_buckets += 1
            continue
        known_keys.add(row.storage_key)
        if row.deleted_at is not None:
            report.pending_purge += 1
        else:
            live[row.storage_key] = str(row.id)

    present: set[str] = set()
    async for key, _last_modified in backend.iter_objects(files.prefix):
        present.add(key)
        if key not in known_keys:
            report.objects_missing_rows.append(key)

    report.rows_missing_objects = [
        (file_id, key) for key, file_id in sorted(live.items()) if key not in present
    ]
    return report


@files_app.command("sweep")
def sweep() -> None:
    """Run the core.sweep_files sweeper now instead of waiting for its cron."""
    settings = get_settings()

    async def _run() -> None:
        engine = create_engine(settings.database_url)
        try:
            files = FileStore.from_settings(settings, session_maker=create_session_maker(engine))
            result = await run_sweep(
                files,
                grace_seconds=settings.files_orphan_grace_seconds,
                now=datetime.now(UTC),
            )
        finally:
            await engine.dispose()
        typer.echo(f"Purged rows: {result.swept_rows}")
        typer.echo(f"Deleted orphan objects: {result.swept_objects}")
        typer.echo(f"Orphans still in grace: {result.skipped_in_grace}")

    asyncio.run(_run())
