import asyncio
import os
import secrets

import typer
from sqlalchemy import func, select

from disp.core.auth.passwords import hash_password
from disp.core.config import get_settings
from disp.core.db import create_engine, create_session_maker
from disp.core.models import User

app = typer.Typer(add_completion=False, help="Server-side admin CLI for disp.")


@app.callback()
def _callback() -> None:
    """Server-side admin CLI for disp."""


@app.command("seed-admin")
def seed_admin(
    email: str = typer.Option(..., "--email", help="Admin email address"),
    display_name: str = typer.Option(..., "--display-name", help="Admin display name"),
) -> None:
    """Create the first admin user. Refuses to run if any user already exists."""
    asyncio.run(_seed_admin(email=email, display_name=display_name))


async def _seed_admin(*, email: str, display_name: str) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_maker = create_session_maker(engine)

    try:
        async with session_maker() as session:
            result = await session.execute(select(func.count()).select_from(User))
            existing_users = result.scalar_one()
            if existing_users > 0:
                typer.secho(
                    "Refusing to seed: a user already exists.",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=1)

            seed_password = os.environ.get("DISP_SEED_PASSWORD")
            generated = seed_password is None
            if seed_password is None:
                seed_password = secrets.token_urlsafe(16)

            user = User(
                email=email,
                display_name=display_name,
                password_hash=hash_password(seed_password),
                is_admin=True,
            )
            session.add(user)
            await session.commit()

        typer.echo(f"Created admin {display_name!r} <{email}>")
        if generated:
            typer.secho(
                f"Generated password (shown once): {seed_password}",
                fg=typer.colors.YELLOW,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    app()
