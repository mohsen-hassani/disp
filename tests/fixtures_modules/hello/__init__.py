from fastapi import APIRouter

from disp.core.contract import (
    ModuleManifest,
    PlatformModule,
    TileContext,
    TileData,
    TileSize,
    TileSpec,
)

MANIFEST = ModuleManifest(
    domain="hello",
    name="Hello",
    version="1.0.0",
    tiles=(TileSpec(key="hello.greeting", title="Hello", size=TileSize.SMALL),),
)


async def _greeting(ctx: TileContext) -> TileData:
    return TileData(
        key="hello.greeting",
        title="Hello",
        count=1,
        items=[],
        actions=[],
        empty_text="hi",
        generated_at=ctx.now,
    )


class HelloModule:
    manifest = MANIFEST

    def register(self, platform: object) -> None:
        return None

    def api_router(self) -> APIRouter | None:
        return None

    def tile_provider(self, key: str) -> object:
        return _greeting if key == "hello.greeting" else None


def get_module() -> PlatformModule:
    return HelloModule()
