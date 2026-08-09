"""Pure-model rules on ModuleManifest's client-surface fields.

No DB, no app — these are the invariants Pydantic enforces at manifest
construction time, which is to say at import time of any module that gets
them wrong. A module with a bad client surface must fail to load at all
rather than shipping a nav entry that points nowhere.
"""

import pytest
from pydantic import ValidationError

from disp.core.contract import ClientNavSpec, ModuleManifest, TileNavSpec, TileSpec


def _manifest(**overrides: object) -> ModuleManifest:
    base: dict[str, object] = {"domain": "widgets", "name": "Widgets", "version": "1.0.0"}
    return ModuleManifest(**{**base, **overrides})  # type: ignore[arg-type]


def test_tile_nav_requires_the_manifest_to_declare_client_nav() -> None:
    """A tile nav button links into /<domain>/..., which only exists because
    the module claimed that namespace. Allowing the button without the claim
    would let a module ship a footer link to screens it never said it had."""
    with pytest.raises(ValidationError, match="declares nav, but the manifest has no client_nav"):
        _manifest(tiles=(TileSpec(key="widgets.due", title="A", nav=TileNavSpec(label="Go")),))


def test_tile_nav_is_accepted_alongside_client_nav() -> None:
    manifest = _manifest(
        tiles=(TileSpec(key="widgets.due", title="A", nav=TileNavSpec(label="Go")),),
        client_nav=ClientNavSpec(label="Widgets"),
    )

    assert manifest.tiles[0].nav is not None
    assert manifest.tiles[0].nav.path == ""


def test_a_tile_without_nav_needs_no_client_nav() -> None:
    """The common case: a module that renders a tile and nothing else stays
    dashboard-only, exactly as before this contract existed."""
    manifest = _manifest(tiles=(TileSpec(key="widgets.due", title="A"),))

    assert manifest.client_nav is None
    assert manifest.tiles[0].nav is None


def test_client_nav_routes_must_be_relative_to_the_module_namespace() -> None:
    """The namespace is derived from the domain, never declared. An absolute
    route here reads as though a module could serve screens at an arbitrary
    path — it can't, because tile deep links are translated by stripping the
    /api prefix, which only ever yields /<domain>/..."""
    with pytest.raises(ValidationError, match="must be relative to /widgets"):
        _manifest(client_nav=ClientNavSpec(label="Widgets", routes=("/widgets/new",)))


def test_client_nav_defaults_are_usable_with_only_a_label() -> None:
    nav = ClientNavSpec(label="Widgets")

    assert nav.icon == "box"  # the client's fallback icon name
    assert nav.order == 100
    assert nav.routes == ()


def test_client_nav_rejects_a_non_kebab_icon_name() -> None:
    """Icon names are looked up in a client-side allow-list keyed by lucide's
    own kebab-case names; anything else can never resolve."""
    with pytest.raises(ValidationError):
        ClientNavSpec(label="Widgets", icon="StickyNote")
