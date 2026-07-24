from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

import disp.modules
from disp.core.config import get_settings
from disp.core.contract import TileContext
from disp.core.registry import ModuleRegistrationError, Registry

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures_modules"


@pytest.fixture(autouse=True)
def _inject_fixture_modules_path() -> Iterator[None]:
    disp.modules.__path__.append(str(FIXTURES_DIR))
    try:
        yield
    finally:
        disp.modules.__path__.remove(str(FIXTURES_DIR))
        get_settings.cache_clear()


def _discover(monkeypatch: MonkeyPatch, modules: str) -> Registry:
    monkeypatch.setenv("MYSTUFF_MODULES", modules)
    get_settings.cache_clear()
    registry = Registry()
    registry.discover()
    return registry


def test_discovery_loads_hello_and_exposes_its_manifest(monkeypatch: MonkeyPatch) -> None:
    registry = _discover(monkeypatch, "hello")

    assert [dm.manifest.domain for dm in registry.modules] == ["hello"]
    assert registry.modules[0].manifest.name == "Hello"
    assert registry.modules[0].manifest.tiles[0].key == "hello.greeting"


def test_module_allow_list_restricts_loading(monkeypatch: MonkeyPatch) -> None:
    registry = _discover(monkeypatch, "hello")

    assert len(registry.modules) == 1
    assert registry.modules[0].manifest.domain == "hello"


def test_unknown_module_in_allow_list_is_fatal(monkeypatch: MonkeyPatch) -> None:
    with pytest.raises(ModuleRegistrationError) as exc_info:
        _discover(monkeypatch, "hello,nonexistent_xyz")

    assert "nonexistent_xyz" in str(exc_info.value)


def test_domain_package_mismatch_is_fatal(monkeypatch: MonkeyPatch) -> None:
    with pytest.raises(ModuleRegistrationError) as exc_info:
        _discover(monkeypatch, "broken_manifest")

    message = str(exc_info.value)
    assert "broken_manifest" in message
    assert "wrong_domain" in message


def test_dependency_cycle_is_fatal_and_names_both_modules(monkeypatch: MonkeyPatch) -> None:
    with pytest.raises(ModuleRegistrationError) as exc_info:
        _discover(monkeypatch, "cyclic_a,cyclic_b")

    message = str(exc_info.value)
    assert "cyclic_a" in message
    assert "cyclic_b" in message


def test_missing_dependency_is_fatal(monkeypatch: MonkeyPatch) -> None:
    with pytest.raises(ModuleRegistrationError) as exc_info:
        _discover(monkeypatch, "cyclic_a")

    message = str(exc_info.value)
    assert "cyclic_a" in message
    assert "cyclic_b" in message


async def test_wiring_indexes_tiles_and_renders_them(monkeypatch: MonkeyPatch) -> None:
    registry = _discover(monkeypatch, "hello")
    registry.wire(app=None, platform=None)

    assert "hello.greeting" in registry.tiles
    assert registry.tiles["hello.greeting"].title == "Hello"

    provider = registry.tile_provider_for("hello.greeting")
    assert provider is not None

    ctx = TileContext(user=None, session=None, platform=None, now=datetime.now(UTC))
    tile_data = await provider(ctx)

    assert tile_data.key == "hello.greeting"
    assert tile_data.count == 1


def test_unknown_tile_provider_returns_none(monkeypatch: MonkeyPatch) -> None:
    registry = _discover(monkeypatch, "hello")
    registry.wire(app=None, platform=None)

    assert registry.tile_provider_for("hello.nonexistent") is None
