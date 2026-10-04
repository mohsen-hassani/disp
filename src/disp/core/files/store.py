"""FileStore — the module-facing facade for core's file/asset service.

Public surface (re-exported from disp.core.files, see docs/milestones/server/
M18-files.md §11): FileStore, StoredFile, AcceptSpec, ACCEPT_IMAGES,
ACCEPT_DOCUMENTS, UsageSummary, get_file_store.
"""

import codecs
import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from fastapi import Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from disp.core.auth import CurrentUser
from disp.core.config import Settings
from disp.core.errors import AppError
from disp.core.files import signing, sniff
from disp.core.models import Asset

CHUNK_SIZE = 64 * 1024


class StorageBackend(Protocol):
    """Where bytes physically live — local disk or S3. See §6."""

    name: str  # "local" | "s3", persisted into assets.backend

    # These are never actually called — Protocol method bodies are pure
    # structural stubs, satisfied by LocalBackend/S3Backend, not executed.
    async def write(self, key: str, chunks: AsyncIterator[bytes]) -> None: ...  # pragma: no cover
    def read(self, key: str) -> AsyncIterator[bytes]: ...  # pragma: no cover
    async def delete(self, key: str) -> None: ...  # pragma: no cover
    async def exists(self, key: str) -> bool: ...  # pragma: no cover

    def iter_objects(  # pragma: no cover
        self, prefix: str = ""
    ) -> AsyncIterator[tuple[str, datetime]]: ...

    def native_signed_url(  # pragma: no cover
        self, key: str, *, content_type: str, expires_in: int
    ) -> str | None: ...


@dataclass(frozen=True)
class AcceptSpec:
    content_types: frozenset[str]
    max_bytes: int


ACCEPT_IMAGES = AcceptSpec(
    frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"}), 5 * 1024 * 1024
)
ACCEPT_DOCUMENTS = AcceptSpec(
    frozenset(
        {
            "application/pdf",
            "text/plain",
            "text/markdown",
            "text/html",
            "application/x-subrip",
        }
    ),
    25 * 1024 * 1024,
)


@dataclass(frozen=True)
class StoredFile:
    """What a module gets back from FileStore — never the ORM row (a module
    holding Asset could reach every other user's assets with one select())."""

    id: uuid.UUID
    domain: str
    purpose: str
    content_type: str
    byte_size: int
    sha256: str
    original_filename: str | None
    created_at: datetime


@dataclass(frozen=True)
class UsageRow:
    domain: str
    purpose: str
    owner_user_id: uuid.UUID
    count: int
    total_bytes: int


@dataclass(frozen=True)
class UsageSummary:
    rows: list[UsageRow]
    total_count: int
    total_bytes: int


def _empty_upload_error() -> AppError:
    return AppError(
        status_code=400,
        code="core.files.empty_upload",
        title="Empty upload",
        detail="The upload contained no bytes.",
    )


def _too_large_error(max_bytes: int) -> AppError:
    return AppError(
        status_code=413,
        code="core.files.too_large",
        title="File too large",
        detail=f"Files must be at most {max_bytes // 1024} KiB.",
    )


def _unsupported_type_error() -> AppError:
    return AppError(
        status_code=415,
        code="core.files.unsupported_type",
        title="Unsupported file type",
        detail="The uploaded bytes are not a supported file type.",
    )


def _not_found_error() -> AppError:
    return AppError(
        status_code=404,
        code="core.files.not_found",
        title="File not found",
        detail="No such file.",
    )


def _missing_object_error() -> AppError:
    return AppError(
        status_code=404,
        code="core.files.missing_object",
        title="File object missing",
        detail="This file's metadata exists but its bytes could not be found.",
    )


async def _iter_source(source: UploadFile | bytes | AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    if isinstance(source, bytes):
        if source:
            yield source
        return
    # A real multipart upload is parsed by Starlette's own parser, which
    # constructs a starlette.datastructures.UploadFile — not the fastapi
    # subclass the public `UploadFile` type hint refers to. isinstance
    # against the fastapi class alone silently misses every real request.
    if isinstance(source, StarletteUploadFile):
        while True:
            chunk = await source.read(CHUNK_SIZE)
            if not chunk:
                return
            yield chunk
        return
    async for chunk in source:
        yield chunk


def _asset_key(
    asset_id: uuid.UUID, *, domain: str, purpose: str, content_type: str, now: datetime
) -> str:
    # No component derives from client input (I4) — domain/purpose are
    # module-chosen labels, asset_id and the date shard are generated here.
    ext = sniff.EXTENSIONS.get(content_type, "")
    return f"{domain}/{purpose}/{now:%Y}/{now:%m}/{asset_id}{ext}"


class FileStore:
    def __init__(self, backend: StorageBackend, *, settings: Settings) -> None:
        self._backend = backend
        self._settings = settings
        self._url_key = signing.derive_key(settings.jwt_secret.get_secret_value())

    @classmethod
    def from_settings(cls, settings: Settings) -> "FileStore":
        """The single construction point for create_app(), worker.py, and the
        disp-admin files CLI — see §7's "third construction context"."""
        if settings.files_backend == "s3":
            # Deferred this pass — see backends/s3.py's absence and §6.2.
            raise RuntimeError("S3 backend not yet implemented — see M18-files.md §6.2")

        from disp.core.files.backends.local import LocalBackend

        backend = LocalBackend(Path(settings.files_root))
        return cls(backend, settings=settings)

    @property
    def backend(self) -> StorageBackend:
        """For core-internal use (the sweeper, `disp-admin files verify`) —
        not part of the module-facing surface."""
        return self._backend

    async def put(
        self,
        session: AsyncSession,
        *,
        owner: CurrentUser | uuid.UUID,
        domain: str,
        purpose: str,
        source: UploadFile | bytes | AsyncIterator[bytes],
        filename: str | None = None,
        accept: AcceptSpec,
        attributes: dict[str, object] | None = None,
    ) -> StoredFile:
        """Streams, validates, writes bytes, adds the row to `session`. Does
        NOT commit — the caller's transaction owns it (I1: bytes before row).

        §7.2: one pass, 64 KiB chunks, peak memory bounded to one chunk plus
        the sniff buffer. The size check on the first chunk happens before
        the backend is ever invoked — a payload whose very first chunk
        already exceeds max_bytes never reaches backend.write.
        """
        max_bytes = min(accept.max_bytes, self._settings.files_max_bytes)
        iterator = _iter_source(source).__aiter__()

        try:
            first_chunk = await iterator.__anext__()
        except StopAsyncIteration:
            raise _empty_upload_error() from None

        head = first_chunk[:16]
        content_type = sniff.sniff(head)
        is_text_family = False
        if content_type is not None:
            if content_type not in accept.content_types:
                raise _unsupported_type_error()
        else:
            # Unsniffable formats write no signature by definition — there's
            # no byte sequence illegal in a .txt file. The declared
            # Content-Type (from the multipart upload) picks which text/*
            # type this is; a strict UTF-8 decode below is the only actual
            # validation available for the text family (§7.1).
            text_candidates = accept.content_types & sniff.TEXT_FAMILY_TYPES
            declared = source.content_type if isinstance(source, StarletteUploadFile) else None
            if declared in text_candidates:
                content_type = declared
            elif len(text_candidates) == 1:
                content_type = next(iter(text_candidates))
            else:
                raise _unsupported_type_error()
            is_text_family = True

        if len(first_chunk) > max_bytes:
            raise _too_large_error(max_bytes)

        digest = hashlib.sha256()
        digest.update(first_chunk)
        byte_size = len(first_chunk)
        decoder = codecs.getincrementaldecoder("utf-8")() if is_text_family else None
        if decoder is not None:
            try:
                decoder.decode(first_chunk)
            except UnicodeDecodeError as exc:
                raise _unsupported_type_error() from exc

        async def _chunks() -> AsyncIterator[bytes]:
            nonlocal byte_size
            yield first_chunk
            async for chunk in iterator:
                byte_size += len(chunk)
                if byte_size > max_bytes:
                    raise _too_large_error(max_bytes)
                if decoder is not None:
                    try:
                        decoder.decode(chunk)
                    except UnicodeDecodeError as exc:
                        raise _unsupported_type_error() from exc
                digest.update(chunk)
                yield chunk

        asset_id = uuid.uuid4()
        now = datetime.now(UTC)
        key = _asset_key(
            asset_id, domain=domain, purpose=purpose, content_type=content_type, now=now
        )

        await self._backend.write(key, _chunks())

        owner_id = owner.id if isinstance(owner, CurrentUser) else owner
        asset = Asset(
            id=asset_id,
            owner_user_id=owner_id,
            domain=domain,
            purpose=purpose,
            content_type=content_type,
            byte_size=byte_size,
            sha256=digest.hexdigest(),
            original_filename=filename,
            backend=self._backend.name,
            storage_key=key,
            attributes=attributes or {},
        )
        session.add(asset)

        return StoredFile(
            id=asset.id,
            domain=asset.domain,
            purpose=asset.purpose,
            content_type=asset.content_type,
            byte_size=asset.byte_size,
            sha256=asset.sha256,
            original_filename=asset.original_filename,
            created_at=now,
        )

    async def get(self, session: AsyncSession, asset_id: uuid.UUID) -> StoredFile | None:
        asset = await session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            return None
        return StoredFile(
            id=asset.id,
            domain=asset.domain,
            purpose=asset.purpose,
            content_type=asset.content_type,
            byte_size=asset.byte_size,
            sha256=asset.sha256,
            original_filename=asset.original_filename,
            created_at=asset.created_at,
        )

    async def open(self, session: AsyncSession, asset_id: uuid.UUID) -> AsyncIterator[bytes]:
        """Distinguishes "no such asset" (core.files.not_found) from "row
        present, bytes gone" (core.files.missing_object) — the distinction
        §15.3's restore scenario depends on."""
        asset = await session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            raise _not_found_error()
        if not await self._backend.exists(asset.storage_key):
            raise _missing_object_error()
        return self._backend.read(asset.storage_key)

    async def delete(self, session: AsyncSession, asset_id: uuid.UUID) -> None:
        """Sets deleted_at. Idempotent. Never touches bytes (I2) — only the
        sweeper removes objects, after the grace period."""
        asset = await session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            return
        asset.deleted_at = datetime.now(UTC)

    def verify_signature(self, asset_id: uuid.UUID, *, exp: int, sig: str) -> bool:
        """Signature-and-expiry check for the signed-URL auth path in
        routes.py. Keeps the derived key encapsulated in FileStore rather
        than exposed to callers."""
        if exp < datetime.now(UTC).timestamp():
            return False
        return signing.verify(asset_id, exp, sig, key=self._url_key)

    def signed_url(self, asset_id: uuid.UUID, *, ttl: int | None = None) -> str:
        """Pure function of the asset id and the bucketed expiry — no I/O, no
        DB access (§7's "requiring the DTO would force a database read to
        mint a URL for an id the caller already holds")."""
        return signing.build_url(
            asset_id,
            key=self._url_key,
            ttl=ttl or self._settings.files_url_ttl_seconds,
            now=datetime.now(UTC),
        )

    async def usage(
        self,
        session: AsyncSession,
        *,
        owner: uuid.UUID | None = None,
        domain: str | None = None,
    ) -> UsageSummary:
        stmt = (
            select(
                Asset.domain,
                Asset.purpose,
                Asset.owner_user_id,
                # Labeled "asset_count", not "count" — Row inherits tuple's
                # own .count() method, which would shadow a same-named
                # attribute and silently break static typing on row access.
                func.count().label("asset_count"),
                func.coalesce(func.sum(Asset.byte_size), 0).label("total_bytes"),
            )
            .where(Asset.deleted_at.is_(None))
            .group_by(Asset.domain, Asset.purpose, Asset.owner_user_id)
        )
        if owner is not None:
            stmt = stmt.where(Asset.owner_user_id == owner)
        if domain is not None:
            stmt = stmt.where(Asset.domain == domain)
        result = await session.execute(stmt)
        rows = [
            UsageRow(
                domain=row.domain,
                purpose=row.purpose,
                owner_user_id=row.owner_user_id,
                count=row.asset_count,
                total_bytes=row.total_bytes,
            )
            for row in result
        ]
        return UsageSummary(
            rows=rows,
            total_count=sum(r.count for r in rows),
            total_bytes=sum(r.total_bytes for r in rows),
        )


def get_file_store(request: Request) -> FileStore:
    """Request-scoped dependency, mirroring settings_store._get_store. §7
    defines this pattern explicitly even though §11's surface table omits
    it — treated as an omission, not a deliberate exclusion (see the M18
    implementation plan)."""
    return request.app.state.platform.files  # type: ignore[no-any-return]
