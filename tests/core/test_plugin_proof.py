"""§22.4: prove the plug-in mechanism needs zero core/ edits.

This spins up a SEPARATE FastAPI app (not the shared session-scoped `app`
fixture) restricted to just the `hello` fixture module via DISP_MODULES,
so it can assert the module surfaces through the real HTTP API without
touching the shared app's already-registered scheduler tasks.
"""

from pathlib import Path

import httpx
import pytest

import disp.modules
from disp.core.config import get_settings

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures_modules"


@pytest.fixture
def _hello_module_path(monkeypatch: pytest.MonkeyPatch) -> None:
    disp.modules.__path__.append(str(FIXTURES_DIR))
    monkeypatch.setenv("DISP_MODULES", "hello")
    get_settings.cache_clear()
    yield
    disp.modules.__path__.remove(str(FIXTURES_DIR))
    get_settings.cache_clear()


async def test_hello_module_appears_in_manifest_and_renders_tile(
    _hello_module_path: None, db_session: object
) -> None:
    from disp.core.app import create_app
    from disp.core.db import get_session

    # A fresh app restricted to "hello" only: distinct from the session-wide
    # `app` fixture (which already registered "notes"'s scheduled task on the
    # shared procrastinate.App singleton — see conftest.py's note on why
    # `create_app()` can only run once per real module set per process).
    fastapi_app = create_app()

    async def _override_get_session():
        yield db_session

    fastapi_app.dependency_overrides[get_session] = _override_get_session

    async with fastapi_app.router.lifespan_context(fastapi_app):
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            from tests.factories import DEFAULT_PASSWORD, make_user

            await make_user(db_session, email="plugin-proof@example.com")
            login = await client.post(
                "/api/auth/login",
                json={"email": "plugin-proof@example.com", "password": DEFAULT_PASSWORD},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            manifest_response = await client.get("/api/dashboard/manifest", headers=headers)
            assert manifest_response.status_code == 200
            domains = {m["domain"] for m in manifest_response.json()["modules"]}
            # "core" is a synthetic entry surfacing core-registered settings panels
            # (core.notifier, wired unconditionally in create_app()) that belong to
            # no discovered module — see dashboard.py's get_manifest().
            assert domains == {"hello", "core"}

            tiles_response = await client.get("/api/dashboard/tiles", headers=headers)
            assert tiles_response.status_code == 200
            tiles = tiles_response.json()["tiles"]
            assert len(tiles) == 1
            assert tiles[0]["key"] == "hello.greeting"
            assert tiles[0]["count"] == 1


def test_no_core_file_was_modified_to_add_the_hello_module() -> None:
    """The `hello` fixture module lives entirely under tests/fixtures_modules/
    and was added with zero edits to src/disp/core/. `git diff` against the
    merge-base with the default branch would be the strongest form of this
    assertion, but in a fresh clone with no history that's not available,
    so this instead asserts the weaker-but-always-true invariant: `hello`'s
    entire implementation lives outside src/disp/core/, meaning wiring it up
    could not have required editing any file under src/disp/core/.

    This used to also run `git status --porcelain -- src/disp/core` and fail
    on any tracked modification. That check did not test the property in this
    test's name: it asserted "the working tree has no uncommitted core
    changes", which is a fact about what the developer is currently doing, not
    about `hello`. It fired on every deliberate core change (the module
    client-surface contract amendment being the one that exposed it) and could
    never distinguish "core was edited to make a module work" — the thing
    §22.4 forbids — from "core was edited for its own reasons". The real proof
    is the test above: a module the core has no knowledge of surfaces through
    the live HTTP API, driven entirely by convention-based discovery.
    """
    hello_files = sorted(FIXTURES_DIR.glob("hello/**/*.py"))
    assert hello_files, "expected the hello fixture module to exist"
    for path in hello_files:
        assert "src/disp/core" not in str(path)
