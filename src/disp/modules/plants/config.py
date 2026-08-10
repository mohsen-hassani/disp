from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class PlantsSettings(BaseSettings):
    """Module-owned configuration.

    Deliberately a separate BaseSettings rather than fields on the core
    `Settings`: a module must not need a core change to be installable, and
    pydantic-settings ignores env vars that don't match this class's own
    `DISP_PLANTS_` prefix (verified — core `Settings`' `extra="forbid"`
    does not trip on them).

    Media storage, sniffing, and the image allow-list moved to
    `disp.core.files` (M18-files.md) — this class keeps only the one
    plants-specific override, an `AcceptSpec.max_bytes` tighter than the
    platform default.
    """

    model_config = SettingsConfigDict(env_prefix="DISP_PLANTS_", env_file=".env", extra="ignore")

    max_image_bytes: int = 2 * 1024 * 1024


@lru_cache
def get_plants_settings() -> PlantsSettings:
    return PlantsSettings()
