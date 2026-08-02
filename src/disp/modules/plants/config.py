from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Uploads are rejected unless the sniffed type is one of these. Kept
# deliberately small: these four cover every camera/phone export, and every
# one of them is safe to serve back with a non-sniffing Content-Type header.
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# (magic-bytes prefix, content type). Checked against the real file contents
# rather than trusting the client-supplied Content-Type header.
_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class PlantsSettings(BaseSettings):
    """Module-owned configuration.

    Deliberately a separate BaseSettings rather than fields on the core
    `Settings`: a module must not need a core change to be installable, and
    pydantic-settings ignores env vars that don't match this class's own
    `DISP_PLANTS_` prefix (verified — core `Settings`' `extra="forbid"`
    does not trip on them).
    """

    model_config = SettingsConfigDict(env_prefix="DISP_PLANTS_", env_file=".env", extra="ignore")

    # Relative paths resolve against the process CWD, which is the repo root
    # for `uv run` and /app in the container.
    media_root: str = "var/media/plants"
    max_image_bytes: int = 2 * 1024 * 1024


@lru_cache
def get_plants_settings() -> PlantsSettings:
    return PlantsSettings()


def media_root() -> Path:
    return Path(get_plants_settings().media_root)


def sniff_image_type(head: bytes) -> str | None:
    """Identify an image from its leading bytes, or None if unrecognised."""
    for prefix, content_type in _MAGIC_PREFIXES:
        if head.startswith(prefix):
            return content_type
    # WebP is RIFF-framed: "RIFF" + 4 size bytes + "WEBP".
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None
