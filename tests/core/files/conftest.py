"""Fixtures for the core file service suite (M18-files.md, Testing).

Every test gets its own key prefix inside the session-wide MinIO bucket
(tests/conftest.py), so a sweeper test's pass B — which deletes every
unreferenced object under the prefix — can never touch another test's
objects.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import BinaryIO
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import Settings, get_settings
from disp.core.files.backends import StorageError
from disp.core.files.store import FileStore

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


@pytest.fixture
def files_settings() -> Settings:
    return get_settings().model_copy(update={"files_s3_prefix": f"t-{uuid4().hex}/"})


@pytest.fixture
def files(files_settings: Settings, session_maker: async_sessionmaker[AsyncSession]) -> FileStore:
    # session_maker joins the per-test transaction, so purges and sweeps see
    # (and roll back with) the test's own rows.
    return FileStore.from_settings(files_settings, session_maker=session_maker)


async def bucket_keys(files: FileStore) -> set[str]:
    return {key async for key, _ in files.backend.iter_objects(files.prefix)}


class SpyBackend:
    """A StorageBackend that records calls instead of touching a bucket."""

    name = "s3"
    bucket = "spy-bucket"

    def __init__(self, *, fail_put: bool = False, fail_delete: bool = False) -> None:
        self.fail_put = fail_put
        self.fail_delete = fail_delete
        self.puts: list[str] = []
        self.deletes: list[tuple[str, str]] = []

    async def put(self, key: str, body: BinaryIO, *, size: int, content_type: str) -> None:
        if self.fail_put:
            raise StorageError("boom")
        self.puts.append(key)

    async def delete(self, bucket: str, key: str) -> None:
        if self.fail_delete:
            raise StorageError("boom")
        self.deletes.append((bucket, key))

    async def iter_objects(self, prefix: str) -> AsyncIterator[tuple[str, datetime]]:
        return
        yield  # pragma: no cover

    def presign_get(
        self,
        bucket: str,
        key: str,
        *,
        ttl: int,
        now: datetime,
        content_type: str,
        content_disposition: str,
    ) -> tuple[str, datetime]:
        raise NotImplementedError  # pragma: no cover


@pytest.fixture
def spy_files(
    files_settings: Settings, session_maker: async_sessionmaker[AsyncSession]
) -> tuple[FileStore, SpyBackend]:
    spy = SpyBackend()
    store = FileStore(
        {"s3": spy}, active="s3", settings=files_settings, session_maker=session_maker
    )
    return store, spy
