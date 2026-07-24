import atexit
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[1]

# Env vars the test suite requires. These are UNCONDITIONAL overrides, not
# `setdefault`: `./dev test` sources the repo's own .env first (dev
# defaults — MYSTUFF_ENV=development, MYSTUFF_RATE_LIMIT_ENABLED=true, a
# dev-only database pointed at the persistent local Postgres, etc.), and
# `setdefault` would silently no-op against anything already present there.
# That previously caused real-rate-limiting to leak into the whole suite
# (running via `./dev test`) even though every individual test file passed
# in isolation via a bare `pytest` invocation that never sourced .env.
# Tests must be hermetic regardless of the invoking shell's environment.
# NOTE: MYSTUFF_DATABASE_URL(_SYNC) are set further below, once the
# testcontainers-managed Postgres 16 container's dynamic port is known.
os.environ["MYSTUFF_JWT_SECRET"] = "test-jwt-secret-please-change-1234567890"  # noqa: S105
os.environ["MYSTUFF_SETTINGS_KEY"] = "ICwTIfRAUP1GgmhgjQhaz44p2hlAM8u9sjW4ELgkTz4="
os.environ["MYSTUFF_BASE_URL"] = "http://localhost:8000"
os.environ["MYSTUFF_ENV"] = "test"
os.environ["MYSTUFF_COOKIE_SECURE"] = "false"
os.environ["MYSTUFF_RATE_LIMIT_ENABLED"] = "false"

# §22.1 requires a real PostgreSQL 16 via testcontainers, started once per
# session. This MUST happen at conftest.py *module import time* (not inside a
# pytest fixture): disp.core.scheduler constructs a procrastinate.App bound to
# MYSTUFF_DATABASE_URL_SYNC at *import time* (see M7's note), and the first
# test module to `from disp.core.app import create_app` (or anything else
# that transitively imports disp.core.scheduler) does so during pytest's
# collection phase — which runs after this file executes top-to-bottom, but
# a fixture body would run later still, after collection, which is too late.
_container = PostgresContainer("postgres:16", driver="asyncpg")
_container.start()
atexit.register(_container.stop)

_ASYNC_URL = _container.get_connection_url()
_SYNC_URL = _ASYNC_URL.replace("+asyncpg", "+psycopg", 1)
os.environ["MYSTUFF_DATABASE_URL"] = _ASYNC_URL
os.environ["MYSTUFF_DATABASE_URL_SYNC"] = _SYNC_URL


def _run(*args: str) -> None:
    subprocess.run(args, cwd=REPO_ROOT, env=os.environ.copy(), check=True)  # noqa: S603


_run(sys.executable, "-m", "alembic", "--name", "core", "upgrade", "head")
_run(sys.executable, "-m", "alembic", "--name", "notes", "upgrade", "head")
_run(sys.executable, "-m", "procrastinate", "--app=disp.core.scheduler.app", "schema", "--apply")

from disp.core.db import create_engine as _create_engine  # noqa: E402
from disp.core.db import get_session  # noqa: E402


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = _create_engine(os.environ["MYSTUFF_DATABASE_URL"])
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_connection(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """One connection + one outer transaction per test; rolled back afterward
    so tests never observe each other's writes (§22.1's "per-test transaction
    rollback" requirement)."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield conn
        await trans.rollback()


@pytest.fixture
def session_maker(db_connection: AsyncConnection) -> async_sessionmaker[AsyncSession]:
    """Bound to the per-test connection via SAVEPOINTs, so any session built
    from it — including ones opened independently of `db_session` below, e.g.
    to simulate a background task's own session — joins the same per-test
    transaction and is rolled back together with it."""
    return async_sessionmaker(
        bind=db_connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    """Session-scoped: `disp.core.scheduler.app` is a process-wide
    procrastinate.App singleton (constructed at import time — see M7's note),
    and `create_app()` registers each module's scheduled tasks onto it by
    name. Calling `create_app()` more than once raises
    SchedulerRegistrationError on the second call (duplicate task name), so
    the FastAPI app itself must be built exactly once per test session; only
    the DB session behind `get_session` varies per test (see `client`)."""
    from disp.core.app import create_app

    fastapi_app = create_app()
    async with fastapi_app.router.lifespan_context(fastapi_app):
        yield fastapi_app


@pytest.fixture
async def client(app: FastAPI, db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        # Mirrors disp.core.db.get_session's own commit-per-request semantics
        # (minus opening a brand-new session): the "commit" here only
        # releases a SAVEPOINT (see db_session's join_transaction_mode), so
        # the outer per-test transaction can still be rolled back afterward.
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_session] = _override_get_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", follow_redirects=False
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_session, None)
