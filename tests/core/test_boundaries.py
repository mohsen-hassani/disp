import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "disp"
MODULES_ROOT = SRC_ROOT / "modules"

# disp.core.auth.__init__'s public surface (§10.1) — the only names any file
# under src/disp/modules/ may import from disp.core.auth.
#
# §10.1's literal code block lists only {CurrentUser, Permission, can,
# current_user, require_admin}. Resolved as an incomplete enumeration: G4 and
# §11.2 require the full ACL API (grant/revoke/list_grants/readable_ids) to be
# "usable by any module", §18.3 explicitly requires the notes module to call
# grant() and readable_ids(), and the boundary's own stated rationale ("makes
# replacing in-app auth with an external OIDC provider a change confined to
# disp/core/auth/") is specific to *authentication*, not ACL/authorization —
# swapping in OIDC never touches acl.py. So the full ACL surface is included
# here; only dependencies.py's `optional_user` and the auth-only submodules
# (tokens/sessions/passwords/invites/schemas/routes/oidc) remain off-limits.
ALLOWED_AUTH_NAMES = {
    "CurrentUser",
    "Permission",
    "can",
    "current_user",
    "grant",
    "list_grants",
    "readable_ids",
    "require",
    "require_admin",
    "revoke",
}

# disp.core.db's sanctioned per-request/per-task session accessors, plus
# `Base`. §8.4 forbids modules from importing "the SQLAlchemy engine" — that
# means create_engine/create_session_maker (which construct a raw, unmanaged
# engine, bypassing the platform's pooling/session pattern), not `Base`: every
# module MUST inherit from the same shared declarative base to define its own
# ORM models at all (this is what lets the M5 alembic `include_object` schema
# filter work — see docs/adding-a-module.md). `metadata` itself stays banned;
# nothing needs to introspect the whole shared MetaData object directly.
ALLOWED_DB_NAMES = {"get_session", "session_scope", "Base"}


def _iter_module_files() -> list[Path]:
    return sorted(MODULES_ROOT.rglob("*.py"))


def _relative(path: Path) -> str:
    return str(path.relative_to(SRC_ROOT.parents[1]))


def _own_domain(path: Path) -> str | None:
    relative_to_modules = path.relative_to(MODULES_ROOT)
    if not relative_to_modules.parts:
        return None
    return relative_to_modules.parts[0]


def test_modules_only_import_public_auth_surface() -> None:
    violations: list[str] = []

    for path in _iter_module_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "disp.core.auth":
                    for alias in node.names:
                        if alias.name not in ALLOWED_AUTH_NAMES:
                            violations.append(
                                f"{_relative(path)}:{node.lineno}: "
                                f"disp.core.auth.{alias.name} is not part of the public surface "
                                f"(allowed: {sorted(ALLOWED_AUTH_NAMES)})"
                            )
                elif node.module is not None and node.module.startswith("disp.core.auth."):
                    violations.append(
                        f"{_relative(path)}:{node.lineno}: importing submodule "
                        f"{node.module!r} is forbidden; only "
                        f"'from disp.core.auth import ...' is allowed"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "disp.core.auth" or alias.name.startswith("disp.core.auth."):
                        violations.append(
                            f"{_relative(path)}:{node.lineno}: 'import {alias.name}' is "
                            f"forbidden; only 'from disp.core.auth import ...' is allowed"
                        )

    assert not violations, "\n".join(violations)


def test_modules_do_not_reach_into_platform_internals() -> None:
    violations: list[str] = []

    for path in _iter_module_files():
        own_domain = _own_domain(path)
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                _check_import_from(path, own_domain, node, violations)
            elif isinstance(node, ast.Import):
                _check_import(path, own_domain, node, violations)

    assert not violations, "\n".join(violations)


def _check_import_from(
    path: Path, own_domain: str | None, node: ast.ImportFrom, violations: list[str]
) -> None:
    if node.module is None:
        return

    if node.module == "disp.core.app" or node.module.startswith("disp.core.app."):
        violations.append(
            f"{_relative(path)}:{node.lineno}: importing {node.module!r} is forbidden"
        )
        return

    if node.module == "disp.core.db":
        for alias in node.names:
            if alias.name not in ALLOWED_DB_NAMES:
                violations.append(
                    f"{_relative(path)}:{node.lineno}: disp.core.db.{alias.name} is forbidden "
                    f"(allowed: {sorted(ALLOWED_DB_NAMES)})"
                )
        return

    if node.module.startswith("disp.modules."):
        _check_cross_module(path, own_domain, node.module, node.lineno, violations)


def _check_import(
    path: Path, own_domain: str | None, node: ast.Import, violations: list[str]
) -> None:
    for alias in node.names:
        name = alias.name
        if name == "disp.core.app" or name.startswith("disp.core.app."):
            violations.append(f"{_relative(path)}:{node.lineno}: 'import {name}' is forbidden")
        elif name == "disp.core.db" or name.startswith("disp.core.db."):
            violations.append(
                f"{_relative(path)}:{node.lineno}: 'import {name}' is forbidden; "
                f"use 'from disp.core.db import get_session'"
            )
        elif name.startswith("disp.modules."):
            _check_cross_module(path, own_domain, name, node.lineno, violations)


def _check_cross_module(
    path: Path, own_domain: str | None, dotted_module: str, lineno: int, violations: list[str]
) -> None:
    parts = dotted_module.split(".")
    other_domain = parts[2] if len(parts) > 2 else None
    if other_domain and other_domain != own_domain:
        violations.append(
            f"{_relative(path)}:{lineno}: importing another module's package "
            f"({dotted_module!r}) is forbidden"
        )
