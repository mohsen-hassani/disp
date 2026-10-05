"""The StorageBackend protocol (M18-files.md §6).

A backend is registered under a stable key (`name`), which is persisted on
every `core.files` row and decides which backend reads and deletes that
row's object. Not part of the module-facing surface — modules never see a
backend.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import BinaryIO, Protocol


class StorageError(Exception):
    """The object store could not complete an operation. FileStore.put turns
    this into `503 core.files.storage_unavailable`; purges and the sweeper log
    it and retry later."""


class StorageBackend(Protocol):
    name: str  # registry key, persisted into core.files.backend
    bucket: str  # where new writes go

    # Protocol method bodies are structural stubs, never executed.
    async def put(  # pragma: no cover
        self, key: str, body: BinaryIO, *, size: int, content_type: str
    ) -> None: ...

    async def delete(self, bucket: str, key: str) -> None: ...  # pragma: no cover

    def iter_objects(  # pragma: no cover
        self, prefix: str
    ) -> AsyncIterator[tuple[str, datetime]]: ...

    def presign_get(  # pragma: no cover
        self,
        bucket: str,
        key: str,
        *,
        ttl: int,
        now: datetime,
        content_type: str,
        content_disposition: str,
    ) -> tuple[str, datetime]: ...
