from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy import create_engine as create_sync_sqlalchemy_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from disp.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    metadata = metadata


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
    )


def create_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    session_maker: async_sessionmaker[AsyncSession] = request.app.state.session_maker
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache
def _background_session_maker() -> async_sessionmaker[AsyncSession]:
    """Lazily-built, process-wide engine/session maker for code with no other
    way to reach one: background tasks (scheduled jobs, deferred jobs) don't
    have a Request to pull `app.state.session_maker` from, and modules aren't
    permitted to import `create_engine`/`create_session_maker` directly."""
    engine = create_engine(get_settings().database_url)
    return create_session_maker(engine)


@asynccontextmanager
async def session_scope(
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncGenerator[AsyncSession]:
    """For background tasks/workers: each task opens its own session, never a
    request one. Pass an explicit `session_maker` when one is already at hand
    (e.g. core code that built it during platform construction); otherwise a
    shared background session maker is built from settings on first use."""
    maker = session_maker if session_maker is not None else _background_session_maker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def create_sync_engine(database_url_sync: str) -> Engine:
    """The psycopg-backed mirror of `create_engine`. Introduced by M22 for the
    sync half of `disp.core.translation` (M22-translation.md §7.1) — a general
    core primitive, not a translation detail.

    Pool size is deliberately smaller than the async engine's: the sync path
    serves one-shot CLI commands and worker-thread callers, not a request
    hot path."""
    return create_sync_sqlalchemy_engine(
        database_url_sync,
        pool_size=2,
        max_overflow=3,
        pool_pre_ping=True,
    )


def create_sync_session_maker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@lru_cache
def _background_sync_session_maker() -> sessionmaker[Session]:
    """Sync counterpart to `_background_session_maker`. `database_url_sync` is
    derived from `database_url` by swapping `+asyncpg` for `+psycopg`
    (config.py's `_derive_database_url_sync`), so this needs no extra
    configuration and no extra dependency — psycopg is already installed for
    Alembic and Procrastinate."""
    return create_sync_session_maker(create_sync_engine(get_settings().database_url_sync))


@contextmanager
def sync_session_scope(
    session_maker: sessionmaker[Session] | None = None,
) -> Iterator[Session]:
    """The sync mirror of `session_scope`, with identical commit/rollback
    semantics. For callers that have no event loop and must not create one:
    Typer commands, Alembic data migrations, and code already running in a
    worker thread (M22-translation.md §5.1)."""
    maker = session_maker if session_maker is not None else _background_sync_session_maker()
    with maker() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
