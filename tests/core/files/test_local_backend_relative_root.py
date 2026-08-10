"""Replicates test_image_survives_a_relative_media_root's exact pattern
(tests/modules/test_plants.py) for DISP_FILES_ROOT.

files_root's default is deliberately relative ("var/media") — a bug where
write() deleted the file it had just written previously survived plants'
entire unit suite because pytest's tmp_path is absolute and pre-resolved;
only monkeypatch.chdir reproduces the shipped-default's actual shape.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from disp.core.config import get_settings
from disp.core.files.store import FileStore


async def test_relative_files_root_survives_a_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISP_FILES_ROOT", "var/media")
    get_settings.cache_clear()
    try:
        files = FileStore.from_settings(get_settings())

        async def chunks() -> AsyncIterator[bytes]:
            yield b"hello"

        await files.backend.write("a/b/c.bin", chunks())

        assert await files.backend.exists("a/b/c.bin")
        data = b""
        async for chunk in files.backend.read("a/b/c.bin"):
            data += chunk
        assert data == b"hello"
    finally:
        get_settings.cache_clear()
