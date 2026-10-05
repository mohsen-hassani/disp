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

# disp.core.files.__init__'s public surface — exactly M18-files.md §11's list.
# UsageRow is exported for core-internal use (routes.py, the admin CLI) but
# isn't part of the module-facing surface — modules only ever see
# UsageSummary as a whole. Backends, sigv4, sweep and store are off-limits.
ALLOWED_FILES_NAMES = {
    "FileStore",
    "StoredFile",
    "FileLink",
    "AcceptSpec",
    "ACCEPT_IMAGES",
    "ACCEPT_DOCUMENTS",
    "ACCEPT_VIDEOS",
    "UsageSummary",
    "get_file_store",
}

# disp.core.llm.__init__'s public surface (M19-llm.md §10). Submodules
# (client, embeddings, usage, budget) are off-limits to modules, like
# disp.core.auth's internals — in particular a module importing
# disp.core.llm.client would be importing the vendor SDK transitively,
# defeating L4 ("a module cannot observe which provider is in use").
ALLOWED_LLM_NAMES = {
    "LLMFacade",
    "LLMCall",
    "FakeLLM",
    "UsageSummary",
    "LLMError",
    "LLMNotConfigured",
    "LLMUnavailable",
    "LLMRefused",
    "LLMTruncated",
    "LLMInvalidOutput",
    "LLMInputTooLarge",
}


# disp.core.translation.__init__'s public surface (M22-translation.md §9).
# Submodules (facade, usage, backends.*) are off-limits to modules — a module
# importing disp.core.translation.backends.deepl would be observing which
# provider is in use, defeating T1.
ALLOWED_TRANSLATION_NAMES = {
    "TranslationFacade",
    "FakeTranslationBackend",
    "Feature",
    "Translated",
    "Detected",
    "UsageSummary",
    "TranslationError",
    "TranslationNotConfigured",
    "TranslationNotSupported",
    "TranslationUnavailable",
    "TranslationQuotaExceeded",
    "TranslationRejected",
    "TranslationInputTooLarge",
    "TranslationInvalidResponse",
}


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


def test_modules_only_import_public_files_surface() -> None:
    violations: list[str] = []

    for path in _iter_module_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "disp.core.files":
                    for alias in node.names:
                        if alias.name not in ALLOWED_FILES_NAMES:
                            violations.append(
                                f"{_relative(path)}:{node.lineno}: "
                                f"disp.core.files.{alias.name} is not part of the public surface "
                                f"(allowed: {sorted(ALLOWED_FILES_NAMES)})"
                            )
                elif node.module is not None and node.module.startswith("disp.core.files."):
                    violations.append(
                        f"{_relative(path)}:{node.lineno}: importing submodule "
                        f"{node.module!r} is forbidden; only "
                        f"'from disp.core.files import ...' is allowed"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "disp.core.files" or alias.name.startswith("disp.core.files."):
                        violations.append(
                            f"{_relative(path)}:{node.lineno}: 'import {alias.name}' is "
                            f"forbidden; only 'from disp.core.files import ...' is allowed"
                        )

    assert not violations, "\n".join(violations)


def test_modules_only_import_public_llm_surface() -> None:
    violations: list[str] = []

    for path in _iter_module_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "disp.core.llm":
                    for alias in node.names:
                        if alias.name not in ALLOWED_LLM_NAMES:
                            violations.append(
                                f"{_relative(path)}:{node.lineno}: "
                                f"disp.core.llm.{alias.name} is not part of the public surface "
                                f"(allowed: {sorted(ALLOWED_LLM_NAMES)})"
                            )
                elif node.module is not None and node.module.startswith("disp.core.llm."):
                    violations.append(
                        f"{_relative(path)}:{node.lineno}: importing submodule "
                        f"{node.module!r} is forbidden; only "
                        f"'from disp.core.llm import ...' is allowed"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "disp.core.llm" or alias.name.startswith("disp.core.llm."):
                        violations.append(
                            f"{_relative(path)}:{node.lineno}: 'import {alias.name}' is "
                            f"forbidden; only 'from disp.core.llm import ...' is allowed"
                        )

    assert not violations, "\n".join(violations)


def test_modules_do_not_import_llm_client() -> None:
    """Narrower restatement of the submodule-forbid branch in
    test_modules_only_import_public_llm_surface, specifically for
    disp.core.llm.client (M19-llm.md §12's explicit ask) — a module
    importing it would import the anthropic SDK transitively (L4)."""
    violations: list[str] = []

    for path in _iter_module_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "disp.core.llm.client":
                violations.append(
                    f"{_relative(path)}:{node.lineno}: importing disp.core.llm.client "
                    f"is forbidden; it transitively imports the anthropic SDK (L4)"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "disp.core.llm.client":
                        violations.append(
                            f"{_relative(path)}:{node.lineno}: 'import disp.core.llm.client' "
                            f"is forbidden; it transitively imports the anthropic SDK (L4)"
                        )

    assert not violations, "\n".join(violations)


def test_anthropic_imported_only_in_client() -> None:
    """M19-llm.md §10: 'anthropic appears in pyproject.toml as a first-class
    dependency and is imported in exactly one file.' Unlike every other
    boundary test in this file, this one walks the whole of src/disp/, not
    just src/disp/modules/ — the requirement is tree-wide, not module-only,
    since core code other than core/llm/client.py must not import the
    vendor SDK either."""
    client_path = SRC_ROOT / "core" / "llm" / "client.py"
    violations: list[str] = []

    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path == client_path:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "anthropic" or alias.name.startswith("anthropic."):
                        violations.append(f"{_relative(path)}:{node.lineno}: import anthropic")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "anthropic" or (
                    node.module is not None and node.module.startswith("anthropic.")
                ):
                    violations.append(f"{_relative(path)}:{node.lineno}: from anthropic import ...")

    assert not violations, "\n".join(violations)


def _public_surface_violations(package: str, allowed: set[str]) -> list[str]:
    """The same AST walk the auth/files/llm tests above spell out inline:
    a name not in the allow-list, a submodule import, or a bare `import`."""
    violations: list[str] = []

    for path in _iter_module_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == package:
                    for alias in node.names:
                        if alias.name not in allowed:
                            violations.append(
                                f"{_relative(path)}:{node.lineno}: "
                                f"{package}.{alias.name} is not part of the public surface "
                                f"(allowed: {sorted(allowed)})"
                            )
                elif node.module is not None and node.module.startswith(f"{package}."):
                    violations.append(
                        f"{_relative(path)}:{node.lineno}: importing submodule "
                        f"{node.module!r} is forbidden; only "
                        f"'from {package} import ...' is allowed"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == package or alias.name.startswith(f"{package}."):
                        violations.append(
                            f"{_relative(path)}:{node.lineno}: 'import {alias.name}' is "
                            f"forbidden; only 'from {package} import ...' is allowed"
                        )

    return violations


def test_modules_only_import_public_translation_surface() -> None:
    violations = _public_surface_violations("disp.core.translation", ALLOWED_TRANSLATION_NAMES)
    assert not violations, "\n".join(violations)


def test_deepl_host_named_in_exactly_one_file() -> None:
    """M22-translation.md §9: T1's enforcement is a *string* grep, not an
    import grep. Because §4.1 chose httpx over the vendor SDK there is no
    `import deepl` to look for — the vendor leaks through the host name
    instead. Scans raw text, comments included."""
    backend_path = SRC_ROOT / "core" / "translation" / "backends" / "deepl.py"
    offenders = [
        _relative(path)
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if path != backend_path and "deepl.com" in path.read_text()
    ]

    assert not offenders, (
        "'deepl.com' must appear only in core/translation/backends/deepl.py, "
        f"also found in: {offenders}"
    )


def test_translation_package_never_runs_an_event_loop() -> None:
    """T3 — the sync surface must not create, enter or require an event loop.
    `asyncio.run` inside a library method raises inside a running loop and
    rebuilds a connection pool per call (M22-translation.md §5.1)."""
    package_root = SRC_ROOT / "core" / "translation"
    offenders = [
        _relative(path)
        for path in sorted(package_root.rglob("*.py"))
        if "asyncio.run" in path.read_text()
    ]

    assert not offenders, f"asyncio.run is forbidden in core/translation/: {offenders}"


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
