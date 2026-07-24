from disp.core.contract import ModuleManifest, PlatformModule

MANIFEST = ModuleManifest(
    domain="cyclic_a",
    name="Cyclic A",
    version="1.0.0",
    dependencies=("cyclic_b",),
)


class CyclicAModule:
    manifest = MANIFEST

    def register(self, platform: object) -> None:
        return None

    def api_router(self) -> None:
        return None

    def tile_provider(self, key: str) -> None:
        return None


def get_module() -> PlatformModule:
    return CyclicAModule()
