"""FileStore — the module-facing facade for core's file service.

See docs/milestones/server/M18-files.md §7. Public surface (re-exported from
disp.core.files, §11): FileStore, StoredFile, FileLink, AcceptSpec,
ACCEPT_IMAGES, ACCEPT_DOCUMENTS, ACCEPT_VIDEOS, UsageSummary, get_file_store.

Modules hand bytes in and get a file id back; they exchange the id for a
presigned link later. They never see a backend, a bucket or a storage key.
"""

import asyncio
import codecs
import hashlib
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import structlog
from fastapi import Request, UploadFile
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import UploadFile as StarletteUploadFile

from disp.core.auth import CurrentUser
from disp.core.config import Settings
from disp.core.db import session_scope
from disp.core.errors import AppError
from disp.core.files import sniff
from disp.core.files.backends import StorageBackend, StorageError
from disp.core.files.sigv4 import MAX_EXPIRES_SECONDS
from disp.core.models import FileRecord

logger = structlog.get_logger(__name__)

CHUNK_SIZE = 64 * 1024
# Past this, the validated upload spools to local temp disk instead of RAM.
SPOOL_MAX_MEMORY = 1024 * 1024
MIN_LINK_TTL_SECONDS = 60
MAX_LINK_TTL_SECONDS = MAX_EXPIRES_SECONDS  # SigV4's 7-day cap

_PENDING_PURGES_KEY = "_disp_files_pending_purges"
_PURGE_LISTENERS_KEY = "_disp_files_purge_listeners"


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
ACCEPT_VIDEOS = AcceptSpec(
    frozenset({"video/mp4", "video/quicktime", "video/webm"}), 100 * 1024 * 1024
)


@dataclass(frozen=True)
class StoredFile:
    """What a module gets back from FileStore — never the ORM row (a module
    holding FileRecord could reach every other user's files with one
    select())."""

    id: uuid.UUID
    domain: str
    purpose: str
    name: str
    content_type: str
    byte_size: int
    sha256: str
    link_ttl_seconds: int
    created_at: datetime


@dataclass(frozen=True)
class FileLink:
    """A presigned bucket URL and the instant it stops working."""

    url: str
    expires_at: datetime


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


def _storage_unavailable_error() -> AppError:
    return AppError(
        status_code=503,
        code="core.files.storage_unavailable",
        title="File storage unavailable",
        detail="The file could not be stored right now. Please try again.",
    )


async def _iter_source(source: UploadFile | bytes | AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    if isinstance(source, bytes):
        for start in range(0, len(source), CHUNK_SIZE):
            yield source[start : start + CHUNK_SIZE]
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
    else:
        async for chunk in source:
            if chunk:
                yield chunk


def _storage_key(
    file_id: uuid.UUID, *, prefix: str, domain: str, purpose: str, content_type: str, now: datetime
) -> str:
    # No component derives from client input (I4) — domain/purpose are
    # module-chosen labels, file_id and the date shard are generated here.
    ext = sniff.EXTENSIONS.get(content_type, "")
    return f"{prefix}{domain}/{purpose}/{now:%Y}/{now:%m}/{file_id}{ext}"


def _sanitize_name(name: str | None, content_type: str) -> str:
    """The display/download name (§4): path components stripped, control
    characters dropped, capped at 255. Used only in Content-Disposition,
    never in a storage key (I4)."""
    if name:
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        base = "".join(ch for ch in base if ch.isprintable()).strip()[:255]
        if base and base not in {".", ".."}:
            return base
    return f"file{sniff.EXTENSIONS.get(content_type, '')}"


def _content_disposition(record: FileRecord) -> str:
    # I6: only a positively sniffed type may be inline. The text family is
    # unsniffable by definition, so it is always attachment.
    disposition = "inline" if record.content_type in sniff.SNIFFABLE_EXTENSIONS else "attachment"
    return f"{disposition}; filename*=UTF-8''{quote(record.name, safe='')}"


def _to_stored(record: FileRecord, *, created_at: datetime | None = None) -> StoredFile:
    return StoredFile(
        id=record.id,
        domain=record.domain,
        purpose=record.purpose,
        name=record.name,
        content_type=record.content_type,
        byte_size=record.byte_size,
        sha256=record.sha256,
        link_ttl_seconds=record.link_ttl_seconds,
        created_at=created_at or record.created_at,
    )


def _discard_pending_purges(sync_session: Any, *_args: Any) -> None:
    sync_session.info.pop(_PENDING_PURGES_KEY, None)


@dataclass
class _Validated:
    content_type: str
    byte_size: int
    sha256: str
    spool: Any  # tempfile.SpooledTemporaryFile[bytes], rewound


class FileStore:
    def __init__(
        self,
        backends: Mapping[str, StorageBackend],
        *,
        active: str,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._backends = dict(backends)
        self._active = self._backends[active]
        self._settings = settings
        self._session_maker = session_maker
        # Strong references to in-flight post-commit purges, so the event
        # loop can't garbage-collect one mid-flight.
        self._purge_tasks: set[asyncio.Task[int]] = set()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> "FileStore":
        """The single construction point for create_app(), worker.py, and the
        disp-admin files CLI. `session_maker` is what post-commit purges and
        the sweeper open their own sessions from; None means the shared
        background one (session_scope's default)."""
        from disp.core.files.backends.s3 import S3Backend

        backend = S3Backend.from_settings(settings)
        return cls(
            {backend.name: backend},
            active=settings.files_backend,
            settings=settings,
            session_maker=session_maker,
        )

    # ------------------------------------------------------------------
    # Core-internal (sweeper, CLI, tests) — not on the module surface.
    # ------------------------------------------------------------------

    @property
    def backend(self) -> StorageBackend:
        """The backend new writes go to."""
        return self._active

    @property
    def prefix(self) -> str:
        return self._settings.files_s3_prefix

    def open_session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return session_scope(self._session_maker)

    def backend_for(self, name: str) -> StorageBackend:
        try:
            return self._backends[name]
        except KeyError:
            raise RuntimeError(f"no storage backend registered under {name!r}") from None

    async def wait_for_purges(self) -> None:
        """Await every in-flight post-commit purge (tests, graceful shutdown)."""
        while self._purge_tasks:
            await asyncio.gather(*self._purge_tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Module-facing API (§7)
    # ------------------------------------------------------------------

    async def put(
        self,
        session: AsyncSession,
        *,
        owner: CurrentUser | uuid.UUID,
        domain: str,
        purpose: str,
        source: UploadFile | bytes | AsyncIterator[bytes],
        name: str | None = None,
        accept: AcceptSpec,
        link_ttl: timedelta | None = None,
        attributes: dict[str, object] | None = None,
    ) -> StoredFile:
        """Validates the whole stream, uploads it in one PutObject, adds the
        row to `session`. Does NOT commit — the caller's transaction owns it
        (I1: bytes before row). A rejected upload never reaches the bucket
        (§7.2)."""
        ttl_seconds = self._resolve_link_ttl(link_ttl)
        max_bytes = min(accept.max_bytes, self._settings.files_max_bytes)
        validated = await self._validate(source, accept=accept, max_bytes=max_bytes)

        file_id = uuid.uuid4()
        now = datetime.now(UTC)
        key = _storage_key(
            file_id,
            prefix=self.prefix,
            domain=domain,
            purpose=purpose,
            content_type=validated.content_type,
            now=now,
        )
        try:
            await self._active.put(
                key,
                validated.spool,
                size=validated.byte_size,
                content_type=validated.content_type,
            )
        except StorageError as exc:
            logger.error("files_put_failed", storage_key=key, exc_info=exc)
            raise _storage_unavailable_error() from exc
        finally:
            validated.spool.close()

        record = FileRecord(
            id=file_id,
            owner_user_id=owner.id if isinstance(owner, CurrentUser) else owner,
            domain=domain,
            purpose=purpose,
            name=_sanitize_name(name, validated.content_type),
            content_type=validated.content_type,
            byte_size=validated.byte_size,
            sha256=validated.sha256,
            backend=self._active.name,
            bucket=self._active.bucket,
            storage_key=key,
            link_ttl_seconds=ttl_seconds,
            attributes=attributes or {},
        )
        session.add(record)
        return _to_stored(record, created_at=now)

    async def get(
        self, session: AsyncSession, file_id: uuid.UUID, *, domain: str
    ) -> StoredFile | None:
        record = await self._live_record(session, file_id, domain=domain)
        return _to_stored(record) if record is not None else None

    async def link(
        self,
        session: AsyncSession,
        file_id: uuid.UUID,
        *,
        domain: str,
        max_ttl: timedelta | None = None,
    ) -> FileLink:
        """A presigned link valid for min(the file's stored ceiling,
        max_ttl) — a reader may shorten, never extend (§9.1)."""
        record = await self._live_record(session, file_id, domain=domain)
        if record is None:
            raise _not_found_error()
        return self._link_for(record, max_ttl=max_ttl, now=datetime.now(UTC))

    async def links(
        self,
        session: AsyncSession,
        file_ids: Iterable[uuid.UUID | None],
        *,
        domain: str,
        max_ttl: timedelta | None = None,
    ) -> dict[uuid.UUID, FileLink]:
        """Batched `link` in one query, for list endpoints. Unknown, deleted
        or foreign-domain ids are simply absent from the result."""
        ids = {file_id for file_id in file_ids if file_id is not None}
        if not ids:
            return {}
        result = await session.execute(
            select(FileRecord).where(
                FileRecord.id.in_(ids),
                FileRecord.domain == domain,
                FileRecord.deleted_at.is_(None),
            )
        )
        now = datetime.now(UTC)
        return {
            record.id: self._link_for(record, max_ttl=max_ttl, now=now)
            for record in result.scalars()
        }

    async def delete(self, session: AsyncSession, file_id: uuid.UUID, *, domain: str) -> None:
        """Marks the row and schedules the post-commit purge (§8.2).
        Idempotent; unknown or foreign-domain ids are a no-op. Never touches
        bytes before commit (I2)."""
        record = await session.get(FileRecord, file_id)
        if record is None or record.domain != domain:
            return
        if record.deleted_at is None:
            record.deleted_at = datetime.now(UTC)
        self._schedule_purge(session, record.id)

    async def usage(
        self,
        session: AsyncSession,
        *,
        owner: uuid.UUID | None = None,
        domain: str | None = None,
    ) -> UsageSummary:
        stmt = (
            select(
                FileRecord.domain,
                FileRecord.purpose,
                FileRecord.owner_user_id,
                # Labeled "file_count", not "count" — Row inherits tuple's
                # own .count() method, which would shadow a same-named
                # attribute and silently break static typing on row access.
                func.count().label("file_count"),
                func.coalesce(func.sum(FileRecord.byte_size), 0).label("total_bytes"),
            )
            .where(FileRecord.deleted_at.is_(None))
            .group_by(FileRecord.domain, FileRecord.purpose, FileRecord.owner_user_id)
        )
        if owner is not None:
            stmt = stmt.where(FileRecord.owner_user_id == owner)
        if domain is not None:
            stmt = stmt.where(FileRecord.domain == domain)
        result = await session.execute(stmt)
        rows = [
            UsageRow(
                domain=row.domain,
                purpose=row.purpose,
                owner_user_id=row.owner_user_id,
                count=row.file_count,
                total_bytes=row.total_bytes,
            )
            for row in result
        ]
        return UsageSummary(
            rows=rows,
            total_count=sum(r.count for r in rows),
            total_bytes=sum(r.total_bytes for r in rows),
        )

    # ------------------------------------------------------------------
    # Purge (§8.2) — also pass A of the sweeper (§8.3)
    # ------------------------------------------------------------------

    async def purge(self, file_ids: Iterable[uuid.UUID] | None = None) -> int:
        """Delete the object, then the row, for every *committed* deletion
        mark (all of them when `file_ids` is None). Runs in a fresh session,
        so an uncommitted mark is invisible and left alone. A storage failure
        on one file is logged and skipped; its mark stays for the next purge
        or sweep. Returns the number of files purged."""
        purged = 0
        async with self.open_session() as session:
            stmt = select(
                FileRecord.id, FileRecord.backend, FileRecord.bucket, FileRecord.storage_key
            ).where(FileRecord.deleted_at.is_not(None))
            if file_ids is not None:
                stmt = stmt.where(FileRecord.id.in_(list(file_ids)))
            rows = (await session.execute(stmt)).all()
            for row in rows:
                try:
                    await self.backend_for(row.backend).delete(row.bucket, row.storage_key)
                except StorageError as exc:
                    logger.error("files_purge_failed", file_id=str(row.id), exc_info=exc)
                    continue
                # A Core DELETE, not session.delete(): a concurrent purge or
                # sweep may already have removed the row, and the ORM would
                # raise StaleDataError on a zero-row delete.
                await session.execute(delete(FileRecord).where(FileRecord.id == row.id))
                purged += 1
        return purged

    def _schedule_purge(self, session: AsyncSession, file_id: uuid.UUID) -> None:
        # Same mechanism as core/events.py's publish_after_commit, but
        # self-contained: it must work in the worker and the CLI too, where
        # no EventBus is guaranteed to be bound.
        sync_session = session.sync_session
        pending: set[uuid.UUID] = sync_session.info.setdefault(_PENDING_PURGES_KEY, set())
        pending.add(file_id)
        if not sync_session.info.get(_PURGE_LISTENERS_KEY):
            sync_session.info[_PURGE_LISTENERS_KEY] = True
            event.listen(sync_session, "after_commit", self._on_commit)
            event.listen(sync_session, "after_rollback", _discard_pending_purges)

    def _on_commit(self, sync_session: Any) -> None:
        file_ids: set[uuid.UUID] | None = sync_session.info.pop(_PENDING_PURGES_KEY, None)
        if not file_ids:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - async sessions always commit inside a loop
            logger.warning("files_purge_no_loop", count=len(file_ids))
            return
        task = loop.create_task(self._purge_logged(frozenset(file_ids)))
        self._purge_tasks.add(task)
        task.add_done_callback(self._purge_tasks.discard)

    async def _purge_logged(self, file_ids: frozenset[uuid.UUID]) -> int:
        try:
            return await self.purge(file_ids)
        except Exception as exc:  # fire-and-forget: the sweeper retries
            logger.error("files_purge_failed", count=len(file_ids), exc_info=exc)
            return 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_link_ttl(self, link_ttl: timedelta | None) -> int:
        if link_ttl is None:
            return self._settings.files_default_link_ttl_seconds
        seconds = int(link_ttl.total_seconds())
        if not MIN_LINK_TTL_SECONDS <= seconds <= MAX_LINK_TTL_SECONDS:
            raise ValueError(
                f"link_ttl must be within {MIN_LINK_TTL_SECONDS}..{MAX_LINK_TTL_SECONDS} "
                f"seconds, got {seconds}"
            )
        return seconds

    async def _live_record(
        self, session: AsyncSession, file_id: uuid.UUID, *, domain: str
    ) -> FileRecord | None:
        record = await session.get(FileRecord, file_id)
        if record is None or record.deleted_at is not None or record.domain != domain:
            return None
        return record

    def _link_for(
        self, record: FileRecord, *, max_ttl: timedelta | None, now: datetime
    ) -> FileLink:
        ttl = record.link_ttl_seconds
        if max_ttl is not None:
            requested = int(max_ttl.total_seconds())
            if requested < 1:
                raise ValueError(f"max_ttl must be at least 1 second, got {max_ttl}")
            ttl = min(ttl, requested)
        url, expires_at = self.backend_for(record.backend).presign_get(
            record.bucket,
            record.storage_key,
            ttl=ttl,
            now=now,
            content_type=record.content_type,
            content_disposition=_content_disposition(record),
        )
        return FileLink(url=url, expires_at=expires_at)

    async def _validate(
        self,
        source: UploadFile | bytes | AsyncIterator[bytes],
        *,
        accept: AcceptSpec,
        max_bytes: int,
    ) -> _Validated:
        """§7.2: one pass in 64 KiB chunks — sniff, size cap mid-stream,
        UTF-8 for the text family, sha256 — into a spool that only reaches
        the bucket once all of it has passed."""
        iterator = _iter_source(source).__aiter__()
        try:
            first_chunk = await iterator.__anext__()
        except StopAsyncIteration:
            raise _empty_upload_error() from None

        content_type = sniff.sniff(first_chunk[: sniff.SNIFF_HEAD_BYTES])
        is_text_family = False
        if content_type is not None:
            if content_type not in accept.content_types:
                raise _unsupported_type_error()
        else:
            # Unsniffable formats write no signature by definition. The
            # declared Content-Type picks which text/* type this is; a strict
            # UTF-8 decode is the only validation available (§7.1).
            text_candidates = accept.content_types & sniff.TEXT_FAMILY_TYPES
            declared = source.content_type if isinstance(source, StarletteUploadFile) else None
            if declared is not None and declared in text_candidates:
                content_type = declared
            elif len(text_candidates) == 1:
                content_type = next(iter(text_candidates))
            else:
                raise _unsupported_type_error()
            is_text_family = True

        decoder = codecs.getincrementaldecoder("utf-8")() if is_text_family else None
        digest = hashlib.sha256()
        byte_size = 0
        spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY)
        try:
            chunk: bytes | None = first_chunk
            while chunk is not None:
                byte_size += len(chunk)
                if byte_size > max_bytes:
                    # Stop reading: the rest of the request body is never
                    # consumed, and nothing has touched the bucket.
                    raise _too_large_error(max_bytes)
                if decoder is not None:
                    try:
                        decoder.decode(chunk)
                    except UnicodeDecodeError as exc:
                        raise _unsupported_type_error() from exc
                digest.update(chunk)
                spool.write(chunk)
                try:
                    chunk = await iterator.__anext__()
                except StopAsyncIteration:
                    chunk = None
            if decoder is not None:
                # A multi-byte sequence truncated at the very end only
                # surfaces on the final flush.
                try:
                    decoder.decode(b"", final=True)
                except UnicodeDecodeError as exc:
                    raise _unsupported_type_error() from exc
            spool.seek(0)
        except BaseException:
            spool.close()
            raise
        return _Validated(
            content_type=content_type,
            byte_size=byte_size,
            sha256=digest.hexdigest(),
            spool=spool,
        )


def get_file_store(request: Request) -> FileStore:
    """Request-scoped dependency, mirroring settings_store._get_store."""
    return request.app.state.platform.files  # type: ignore[no-any-return]
