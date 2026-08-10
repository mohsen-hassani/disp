"""Fixture module deliberately claiming the reserved "files" domain — used
by tests/core/test_registry.py to assert Registry.discover() rejects it
(M18-files.md §10: a module here would collide with the core /api/files
router)."""

from fastapi import APIRouter

from disp.core.contract import ModuleManifest, PlatformModule

MANIFEST = ModuleManifest(domain="files", name="Files", version="1.0.0")


class FilesModule:
    manifest = MANIFEST

    def register(self, platform: object) -> None:
        return None

    def api_router(self) -> APIRouter | None:
        return None

    def tile_provider(self, key: str) -> object:
        return None


def get_module() -> PlatformModule:
    return FilesModule()
