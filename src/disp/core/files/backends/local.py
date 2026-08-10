"""Local filesystem StorageBackend (M18-files.md §6.1).

Generalises plants/storage.py, but three things here are improvements, not a
straight port: fsync before rename (plants had none), a random temp-file
suffix (plants used a deterministic one, so two concurrent uploads for one
plant could collide), and `unlink(missing_ok=True)` (plants pre-checked
`.exists()`, a TOCTOU race).
"""

import os
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from disp.core.files.store import CHUNK_SIZE


def _ensure_inside(root: Path, candidate: Path) -> Path:
    # Belt-and-braces (I4): no key component ever derives from client input,
    # so this should never trigger — it exists for the day that stops being
    # true, same reasoning as plants/storage.py's original.
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"refusing to touch {candidate} outside the media root")
    return resolved


class LocalBackend:
    name = "local"

    def __init__(self, root: Path) -> None:
        self._root = root

    async def write(self, key: str, chunks: AsyncIterator[bytes]) -> None:
        target = _ensure_inside(self._root, self._root / key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.parent / f"{target.name}.{secrets.token_hex(8)}.tmp"
        try:
            with temp.open("wb") as fh:
                async for chunk in chunks:
                    fh.write(chunk)
                fh.flush()
                os.fsync(fh.fileno())
            temp.replace(target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    async def read(self, key: str) -> AsyncIterator[bytes]:
        path = _ensure_inside(self._root, self._root / key)
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    return
                yield chunk

    async def delete(self, key: str) -> None:
        path = _ensure_inside(self._root, self._root / key)
        path.unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        path = _ensure_inside(self._root, self._root / key)
        return path.is_file()

    async def iter_objects(self, prefix: str = "") -> AsyncIterator[tuple[str, datetime]]:
        base = _ensure_inside(self._root, self._root / prefix)
        if not base.is_dir():
            return
        root = self._root.resolve()
        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                if filename.endswith(".tmp"):
                    continue
                full = (Path(dirpath) / filename).resolve()
                relative = full.relative_to(root)
                stat = full.stat()
                yield relative.as_posix(), datetime.fromtimestamp(stat.st_mtime, tz=UTC)

    def native_signed_url(self, key: str, *, content_type: str, expires_in: int) -> str | None:
        return None
