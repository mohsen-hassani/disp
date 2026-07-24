import importlib
import pkgutil
from typing import TYPE_CHECKING, NoReturn

import structlog
from fastapi import APIRouter, FastAPI

from disp.core.config import get_settings
from disp.core.contract import (
    ModuleManifest,
    NotificationTypeSpec,
    PlatformModule,
    ScheduledJobSpec,
    SettingsPanelSpec,
    TileProvider,
    TileSpec,
)
from disp.core.scheduler import SchedulerRegistrationError

if TYPE_CHECKING:
    from disp.core.platform import Platform

logger = structlog.get_logger(__name__)


class ModuleRegistrationError(Exception):
    pass


def _fatal(message: str) -> NoReturn:
    logger.critical("module_registration_fatal", message=message)
    raise ModuleRegistrationError(message)


class DiscoveredModule:
    __slots__ = ("instance", "manifest")

    def __init__(self, manifest: ModuleManifest, instance: PlatformModule) -> None:
        self.manifest = manifest
        self.instance = instance


class Registry:
    """Module discovery, validation, dependency ordering, and wiring (§9)."""

    def __init__(self) -> None:
        self.modules: list[DiscoveredModule] = []
        self.tiles: dict[str, TileSpec] = {}
        self.settings_panels: dict[str, SettingsPanelSpec] = {}
        self.scheduled_jobs: list[ScheduledJobSpec] = []
        self.notification_types: dict[str, NotificationTypeSpec] = {}
        self._tile_owner: dict[str, PlatformModule] = {}

    # ------------------------------------------------------------------
    # Discovery (§9.1)
    # ------------------------------------------------------------------

    def discover(self) -> None:
        import disp.modules as modules_pkg

        candidate_names = sorted(name for _, name, _ in pkgutil.iter_modules(modules_pkg.__path__))

        allow_list = get_settings().module_allow_list
        if allow_list:
            unknown = sorted(set(allow_list) - set(candidate_names))
            if unknown:
                _fatal(f"MYSTUFF_MODULES names unknown module(s): {unknown}")
            allowed = set(allow_list)
            candidate_names = [name for name in candidate_names if name in allowed]

        discovered = [self._load_candidate(name) for name in candidate_names]
        self._validate_global_uniqueness(discovered)
        self.modules = self._topological_sort(discovered)

    def _load_candidate(self, name: str) -> DiscoveredModule:
        try:
            module = importlib.import_module(f"disp.modules.{name}")
        except ImportError as exc:
            _fatal(f"module {name!r} failed to import: {exc}")

        get_module = getattr(module, "get_module", None)
        if not callable(get_module):
            _fatal(f"module {name!r} does not expose a callable get_module()")

        instance = get_module()
        manifest = getattr(instance, "manifest", None)
        if not isinstance(manifest, ModuleManifest):
            _fatal(
                f"module {name!r}'s get_module() must return an object whose "
                f"'manifest' attribute is a ModuleManifest instance"
            )

        if manifest.domain != name:
            _fatal(
                f"module {name!r} has manifest.domain={manifest.domain!r}, "
                f"which must match its package name"
            )

        return DiscoveredModule(manifest=manifest, instance=instance)

    def _validate_global_uniqueness(self, discovered: list[DiscoveredModule]) -> None:
        domains_seen: dict[str, str] = {}
        tile_keys: dict[str, str] = {}
        panel_keys: dict[str, str] = {}
        job_names: dict[str, str] = {}
        notification_keys: dict[str, str] = {}

        for dm in discovered:
            manifest = dm.manifest
            if manifest.domain in domains_seen:
                _fatal(f"duplicate module domain {manifest.domain!r}")
            domains_seen[manifest.domain] = manifest.domain

            for tile in manifest.tiles:
                if tile.key in tile_keys:
                    _fatal(
                        f"duplicate tile key {tile.key!r} (modules "
                        f"{tile_keys[tile.key]!r} and {manifest.domain!r})"
                    )
                tile_keys[tile.key] = manifest.domain

            for panel in manifest.settings_panels:
                if panel.key in panel_keys:
                    _fatal(
                        f"duplicate settings panel key {panel.key!r} (modules "
                        f"{panel_keys[panel.key]!r} and {manifest.domain!r})"
                    )
                panel_keys[panel.key] = manifest.domain

            for job in manifest.scheduled_jobs:
                if job.name in job_names:
                    _fatal(
                        f"duplicate scheduled job name {job.name!r} (modules "
                        f"{job_names[job.name]!r} and {manifest.domain!r})"
                    )
                job_names[job.name] = manifest.domain

            for notification_type in manifest.notification_types:
                if notification_type.key in notification_keys:
                    _fatal(
                        f"duplicate notification type key {notification_type.key!r} "
                        f"(modules {notification_keys[notification_type.key]!r} "
                        f"and {manifest.domain!r})"
                    )
                notification_keys[notification_type.key] = manifest.domain

        known_domains = set(domains_seen)
        for dm in discovered:
            for dependency in dm.manifest.dependencies:
                if dependency not in known_domains:
                    _fatal(
                        f"module {dm.manifest.domain!r} depends on unknown module {dependency!r}"
                    )

    def _topological_sort(self, discovered: list[DiscoveredModule]) -> list[DiscoveredModule]:
        by_domain = {dm.manifest.domain: dm for dm in discovered}
        in_degree = dict.fromkeys(by_domain, 0)
        dependents: dict[str, list[str]] = {domain: [] for domain in by_domain}

        for dm in discovered:
            for dependency in dm.manifest.dependencies:
                in_degree[dm.manifest.domain] += 1
                dependents[dependency].append(dm.manifest.domain)

        ready = sorted(domain for domain, degree in in_degree.items() if degree == 0)
        ordered_domains: list[str] = []

        while ready:
            domain = ready.pop(0)
            ordered_domains.append(domain)
            for dependent in sorted(dependents[domain]):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)
            ready.sort()

        if len(ordered_domains) != len(discovered):
            remaining = sorted(set(by_domain) - set(ordered_domains))
            _fatal(f"dependency cycle detected among module(s): {remaining}")

        return [by_domain[domain] for domain in ordered_domains]

    # ------------------------------------------------------------------
    # Wiring (§9.2)
    # ------------------------------------------------------------------

    def wire(self, app: FastAPI | None, platform: "Platform") -> None:
        """`app` is None in the worker process (§9.4), which wires tasks and
        event handlers but never serves HTTP, so there is no router to mount."""
        for dm in self.modules:
            dm.instance.register(platform)

            router = dm.instance.api_router()
            if router is not None and app is not None:
                self._include_router(app, router, dm.manifest.domain)

            for job in dm.manifest.scheduled_jobs:
                try:
                    platform.scheduler.register_periodic(job.name, job.cron)
                except SchedulerRegistrationError as exc:
                    _fatal(str(exc))
                self.scheduled_jobs.append(job)

            for tile in dm.manifest.tiles:
                self.tiles[tile.key] = tile
                self._tile_owner[tile.key] = dm.instance

            for panel in dm.manifest.settings_panels:
                self.settings_panels[panel.key] = panel

            for notification_type in dm.manifest.notification_types:
                self.notification_types[notification_type.key] = notification_type

    def _include_router(self, app: FastAPI, router: APIRouter, domain: str) -> None:
        app.include_router(router, prefix=f"/api/{domain}", tags=[domain])

    # ------------------------------------------------------------------
    # Core built-ins (not discovered via disp.modules — see M7/M9 registration gap)
    # ------------------------------------------------------------------

    def register_core_scheduled_job(self, job: ScheduledJobSpec) -> None:
        self.scheduled_jobs.append(job)

    def register_core_settings_panel(self, panel: SettingsPanelSpec) -> None:
        self.settings_panels[panel.key] = panel

    # ------------------------------------------------------------------
    # Read-only accessors (§8.4)
    # ------------------------------------------------------------------

    def tile_provider_for(self, key: str) -> TileProvider | None:
        owner = self._tile_owner.get(key)
        if owner is None:
            return None
        return owner.tile_provider(key)

    def settings_panel_for_domain(self, domain: str) -> SettingsPanelSpec | None:
        for panel in self.settings_panels.values():
            panel_domain, _, _ = panel.key.partition(".")
            if panel_domain == domain:
                return panel
        return None
