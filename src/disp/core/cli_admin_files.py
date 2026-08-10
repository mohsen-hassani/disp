"""`disp-admin files ...` — operational commands for the core file/asset
service (M18-files.md §12, §15.3). No Platform in CLI context, so every
command builds its own engine/session-maker, mirroring seed_admin in
cli_admin.py.
"""

import asyncio
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from disp.core.config import get_settings
from disp.core.db import create_engine, create_session_maker
from disp.core.errors import AppError
from disp.core.files.store import ACCEPT_IMAGES, FileStore
from disp.core.models import Asset

files_app = typer.Typer(add_completion=False, help="Manage the core file/asset service.")


@files_app.command("adopt")
def adopt(
    domain: Annotated[str, typer.Option("--domain", help="Asset domain to adopt files into")],
    purpose: Annotated[str, typer.Option("--purpose", help="Asset purpose to adopt files into")],
    root: Annotated[Path, typer.Option("--root", help="Pre-existing media root to walk")],
) -> None:
    """Backfill core.assets from a module's pre-M18 ad-hoc media storage.

    Idempotent and re-runnable — prints a summary rather than assuming
    success. Only `--domain plants` is supported: ownership resolution is
    necessarily domain-specific (there is no generic way to find who owns an
    orphaned file on disk), and plants is the only module this milestone
    ports (M18-files.md §12).
    """
    if domain != "plants":
        typer.secho(
            f"adopt only supports --domain plants today (got {domain!r}) — ownership "
            "resolution is domain-specific and there is no generic implementation yet",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    asyncio.run(_adopt_plants(purpose=purpose, root=root))


async def _adopt_plants(*, purpose: str, root: Path) -> None:
    # Cross-schema read from CLI code, not module code — the module-boundary
    # AST check (tests/core/test_boundaries.py) only scans src/disp/modules/,
    # so this is exempt; it is still a deliberate, narrow exception to "core
    # doesn't know about specific modules", scoped to this one migration tool.
    from disp.modules.plants.models import Plant

    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_maker = create_session_maker(engine)
    files = FileStore.from_settings(settings)

    adopted: list[str] = []
    already_adopted = 0
    orphaned: list[str] = []
    errors: list[str] = []

    try:
        async with session_maker() as session:
            if not root.is_dir():
                typer.secho(f"No such directory: {root}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)

            for path in sorted(root.iterdir()):
                if not path.is_file():
                    continue
                try:
                    plant_id = UUID(path.stem)
                except ValueError:
                    orphaned.append(path.name)
                    continue

                plant = await session.get(Plant, plant_id)
                if plant is None:
                    orphaned.append(path.name)
                    continue
                if plant.image_asset_id is not None:
                    already_adopted += 1
                    continue

                data = path.read_bytes()
                try:
                    stored = await files.put(
                        session,
                        owner=plant.user_id,
                        domain="plants",
                        purpose=purpose,
                        source=data,
                        filename=path.name,
                        accept=ACCEPT_IMAGES,
                    )
                except AppError as exc:
                    errors.append(f"{path.name}: {exc.detail}")
                    continue

                plant.image_asset_id = stored.id
                adopted.append(path.name)

            await session.commit()
    finally:
        await engine.dispose()

    typer.echo(f"Adopted: {len(adopted)}")
    typer.echo(f"Already adopted (skipped): {already_adopted}")
    typer.echo(f"Orphaned (no matching plant): {len(orphaned)}")
    for name in orphaned:
        typer.secho(f"  {name}", fg=typer.colors.YELLOW)
    if errors:
        typer.echo(f"Errors: {len(errors)}")
        for err in errors:
            typer.secho(f"  {err}", fg=typer.colors.RED)


@files_app.command("verify")
def verify() -> None:
    """Report assets whose rows have no backing object, and objects with no
    row. Deletes nothing (I3) — the first thing to run after any restore
    (§15.3): a mistaken-deletion here would turn a recoverable mount error
    into permanent metadata loss.
    """
    asyncio.run(_verify())


async def _verify() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_maker = create_session_maker(engine)
    files = FileStore.from_settings(settings)

    try:
        async with session_maker() as session:
            rows_missing_objects, objects_missing_rows = await _diff(session, files)
    finally:
        await engine.dispose()

    typer.echo(f"Rows with no backing object: {len(rows_missing_objects)}")
    for asset_id, storage_key in rows_missing_objects:
        typer.secho(f"  {asset_id}  {storage_key}", fg=typer.colors.YELLOW)

    typer.echo(f"Objects with no row: {len(objects_missing_rows)}")
    for key in objects_missing_rows:
        typer.secho(f"  {key}", fg=typer.colors.YELLOW)

    if not rows_missing_objects and not objects_missing_rows:
        typer.secho(
            "Clean: every row has an object, every object has a row.", fg=typer.colors.GREEN
        )


async def _diff(session: AsyncSession, files: FileStore) -> tuple[list[tuple[str, str]], list[str]]:
    result = await session.execute(select(Asset).where(Asset.deleted_at.is_(None)))
    assets = list(result.scalars())

    rows_missing_objects: list[tuple[str, str]] = []
    known_keys: set[str] = set()
    for asset in assets:
        known_keys.add(asset.storage_key)
        if not await files.backend.exists(asset.storage_key):
            rows_missing_objects.append((str(asset.id), asset.storage_key))

    objects_missing_rows: list[str] = [
        key async for key, _last_modified in files.backend.iter_objects() if key not in known_keys
    ]

    return rows_missing_objects, objects_missing_rows
