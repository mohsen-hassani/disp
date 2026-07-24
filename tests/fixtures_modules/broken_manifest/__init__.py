from disp.core.contract import ModuleManifest, PlatformModule

# Deliberately wrong: the package is named "broken_manifest" but the manifest
# declares a different domain, exercising the domain/package-name mismatch
# fatal error (§9.1 step 6, test case 30).
MANIFEST = ModuleManifest(domain="wrong_domain", name="Broken", version="1.0.0")


class BrokenManifestModule:
    manifest = MANIFEST

    def register(self, platform: object) -> None:
        return None

    def api_router(self) -> None:
        return None

    def tile_provider(self, key: str) -> None:
        return None


def get_module() -> PlatformModule:
    return BrokenManifestModule()
