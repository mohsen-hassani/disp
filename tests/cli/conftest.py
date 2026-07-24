import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def cli_transport(app: FastAPI) -> Iterator[object]:
    """A sync-callable ASGI transport backed by ONE long-lived anyio portal
    (thread + event loop) for the whole test.

    Using `starlette.testclient.TestClient(app)._transport` directly doesn't
    work here: unless `TestClient` is entered as a context manager, its
    `_portal_factory` spins up a BRAND NEW portal (and event loop) for every
    single request, tearing it down again immediately after — so a second
    request over the same transport hits "Event loop is closed" (the
    CLI-dedicated engine's asyncpg connections, bound to the first request's
    now-closed loop, can't be reused by the second). Entering `TestClient`
    itself as a context manager isn't an option either: that also re-runs the
    ASGI lifespan (`_wait_for_database`, `procrastinate_app.open_async()`) a
    second time on an app whose lifespan the session-scoped `app` fixture
    already started. So this builds the lower-level `_TestClientTransport`
    directly, with a `portal_factory` that always returns the SAME portal.
    """
    import contextlib

    import anyio.from_thread
    from starlette.testclient import _TestClientTransport

    with anyio.from_thread.start_blocking_portal(backend="asyncio") as portal:

        @contextlib.contextmanager
        def _reuse_portal():
            yield portal

        transport = _TestClientTransport(
            app,
            portal_factory=_reuse_portal,
            raise_server_exceptions=True,
            root_path="",
            client=("testclient", 50000),
            app_state={},
        )
        yield transport


@pytest.fixture(scope="session")
async def _cli_setup_engine():
    from disp.core.db import create_engine as disp_create_engine

    eng = disp_create_engine(os.environ["MYSTUFF_DATABASE_URL"])
    yield eng
    await eng.dispose()


@pytest.fixture
async def cli_db(_cli_setup_engine: object) -> AsyncIterator[AsyncSession]:
    """A REAL-commit session (not the per-test-rollback `db_session`) for
    seeding data CLI tests need. `db_session` is bound to this test's
    connection via a SAVEPOINT, so its "commits" never leave an uncommitted
    outer transaction — invisible to any other real connection. But the CLI's
    own requests run through `cli_transport`'s separate portal thread/loop,
    which must use its OWN physically separate connection (asyncpg
    connections are loop-affine, so it can't share `db_session`'s). Fixtures
    used to seed data the CLI needs to see must therefore actually commit,
    which is what this session does."""
    from disp.core.db import create_session_maker

    maker = create_session_maker(_cli_setup_engine)  # type: ignore[arg-type]
    async with maker() as session:
        yield session


@pytest.fixture
def cli_env(
    app: FastAPI, cli_transport: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Points every CLI command's ApiClient at the in-process ASGI app (via
    `cli_transport`) instead of a real network port (§22.1), and isolates the
    CLI's config file into a per-test tmp_path (platformdirs respects
    XDG_CONFIG_HOME on this platform).

    `cli_transport` bridges the CLI's *sync* httpx.Client to the *async* ASGI
    app via a background-thread "portal" (Starlette's TestClient machinery).
    That portal runs its own event loop, distinct from this test session's
    loop — so `db_session` (asyncpg-bound to the session loop) cannot be used
    to serve requests dispatched through it (asyncpg connections are
    loop-affine). Instead, `get_session` is overridden here with a session
    built from a *separate* engine whose connections are only ever opened
    lazily, from within the portal thread on first request — keeping it
    consistently on the portal's own loop. Setup (creating users/PATs) and
    post-hoc assertions still go through the ordinary `db_session` fixture;
    both engines point at the same testcontainers Postgres, so writes from
    one are visible to the other via ordinary commit/read-committed
    semantics, without sharing any loop-bound Python objects.
    """
    import disp.cli.commands.auth as auth_module
    import disp.cli.state as state_module
    from disp.cli.client import ApiClient
    from disp.core.db import create_engine as disp_create_engine
    from disp.core.db import create_session_maker, get_session

    cli_engine = disp_create_engine(os.environ["MYSTUFF_DATABASE_URL"])
    cli_session_maker = create_session_maker(cli_engine)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with cli_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = _override_get_session

    class _TransportApiClient(ApiClient):
        def __init__(self, config: object) -> None:
            super().__init__(config, transport=cli_transport)  # type: ignore[arg-type]

    monkeypatch.setattr(state_module, "ApiClient", _TransportApiClient)
    monkeypatch.setattr(auth_module, "ApiClient", _TransportApiClient)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Rich's color auto-detection honours FORCE_COLOR (force-color.org)
    # ahead of isatty(), so a shell with FORCE_COLOR set (as this sandbox's
    # does) would otherwise leak ANSI escapes into CliRunner's captured
    # output even though it isn't a real terminal — which is exactly the
    # non-interactive/piped scenario §19.2 promises stays plain.
    monkeypatch.delenv("FORCE_COLOR", raising=False)

    yield "http://testserver"

    app.dependency_overrides.pop(get_session, None)
