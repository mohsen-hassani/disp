"""Backend conformance suite (M18-files.md §14).

Local backend only this pass — S3 is deferred (see FileStore.from_settings).
Structured so adding S3 later is additive: parametrize the `backend` fixture
once backends/s3.py lands, rather than rewriting these assertions.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from disp.core.files.backends.local import LocalBackend


@pytest.fixture
def backend(tmp_path: Path) -> LocalBackend:
    return LocalBackend(tmp_path)


async def _drain(chunks: AsyncIterator[bytes]) -> bytes:
    data = b""
    async for chunk in chunks:
        data += chunk
    return data


async def _single_chunk(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


async def test_round_trip(backend: LocalBackend) -> None:
    await backend.write("a/b/c.bin", _single_chunk(b"hello world"))
    assert await backend.exists("a/b/c.bin")
    assert await _drain(backend.read("a/b/c.bin")) == b"hello world"


async def test_write_is_atomic_or_absent(backend: LocalBackend, tmp_path: Path) -> None:
    class BoomError(Exception):
        pass

    async def broken_chunks() -> AsyncIterator[bytes]:
        yield b"partial"
        raise BoomError

    with pytest.raises(BoomError):
        await backend.write("a/b/broken.bin", broken_chunks())

    assert not await backend.exists("a/b/broken.bin")
    assert list(tmp_path.rglob("*.tmp")) == []


async def test_delete_is_idempotent(backend: LocalBackend) -> None:
    await backend.delete("nope.bin")  # never existed

    await backend.write("a.bin", _single_chunk(b"x"))
    await backend.delete("a.bin")
    await backend.delete("a.bin")  # already gone

    assert not await backend.exists("a.bin")


async def test_iter_objects_shape_and_skips_tmp_artifacts(
    backend: LocalBackend, tmp_path: Path
) -> None:
    await backend.write("a/b/c.bin", _single_chunk(b"x"))
    (tmp_path / "a" / "b" / "stray.tmp").write_bytes(b"leftover")

    objects = [obj async for obj in backend.iter_objects()]

    assert {key for key, _ in objects} == {"a/b/c.bin"}
    _key, last_modified = objects[0]
    assert isinstance(last_modified, datetime)
    assert last_modified.tzinfo is UTC


async def test_native_signed_url_is_always_none(backend: LocalBackend) -> None:
    assert backend.native_signed_url("a.bin", content_type="image/png", expires_in=60) is None


def test_ensure_inside_rejects_a_path_outside_the_root(tmp_path: Path) -> None:
    from disp.core.files.backends.local import _ensure_inside

    outside = tmp_path.parent / "definitely-outside-the-root"
    with pytest.raises(ValueError, match="outside the media root"):
        _ensure_inside(tmp_path, outside)


async def test_iter_objects_on_a_root_that_does_not_exist_yet(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "never-written-to")
    objects = [obj async for obj in backend.iter_objects()]
    assert objects == []
