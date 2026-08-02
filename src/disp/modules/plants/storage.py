from pathlib import Path
from uuid import UUID

from disp.modules.plants.config import ALLOWED_IMAGE_TYPES, media_root

# Filenames are derived entirely from the plant's UUID and a content type this
# module chose from a fixed allow-list — no part of a filename ever comes from
# client input, so there is no traversal surface here. `_ensure_inside` is a
# belt-and-braces check in case that ever stops being true.


def _ensure_inside(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"refusing to touch {candidate} outside the media root")
    return resolved


def relative_path(plant_id: UUID, content_type: str) -> str:
    return f"{plant_id}{ALLOWED_IMAGE_TYPES[content_type]}"


def absolute_path(relative: str) -> Path:
    root = media_root()
    return _ensure_inside(root, root / relative)


def _variant_paths(plant_id: UUID) -> list[Path]:
    """Every path this plant's image could occupy, one per allowed extension.

    Resolved, like everything `_ensure_inside` returns: the configured media
    root is relative by default (`var/media/plants`), so an unresolved path
    built here would never compare equal to the resolved target in
    `write_image` — and the cleanup loop there would delete the file it had
    just written.
    """
    root = media_root()
    return [_ensure_inside(root, root / f"{plant_id}{ext}") for ext in ALLOWED_IMAGE_TYPES.values()]


def write_image(plant_id: UUID, data: bytes, content_type: str) -> str:
    """Write the image and drop any previously stored variant.

    Re-uploading a PNG over a JPEG changes the extension, so the old file is
    removed explicitly rather than left orphaned next to the new one.
    """
    root = media_root()
    root.mkdir(parents=True, exist_ok=True)

    relative = relative_path(plant_id, content_type)
    target = _ensure_inside(root, root / relative)

    # Write to a temp file in the same directory, then rename: a crash or a
    # failed write can never leave a half-written image being served.
    temp = target.with_name(f".{target.name}.tmp")
    temp.write_bytes(data)
    temp.replace(target)

    for stale in _variant_paths(plant_id):
        if stale != target and stale.exists():
            stale.unlink()
    return relative


def remove_image(plant_id: UUID) -> None:
    for path in _variant_paths(plant_id):
        if path.exists():
            path.unlink()
