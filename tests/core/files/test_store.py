"""FileStore put/get/link/links/delete/usage against MinIO (M18-files.md §7, §9)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from disp.core.config import Settings, get_settings
from disp.core.errors import AppError
from disp.core.files.store import (
    ACCEPT_DOCUMENTS,
    ACCEPT_IMAGES,
    ACCEPT_VIDEOS,
    AcceptSpec,
    FileStore,
)
from disp.core.models import FileRecord
from tests.core.files.conftest import PNG_1PX, SpyBackend, bucket_keys
from tests.factories import make_user


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def _put_png(files: FileStore, session: AsyncSession, owner: Any, **kwargs: Any) -> Any:
    return await files.put(
        session,
        owner=owner,
        domain=kwargs.pop("domain", "plants"),
        purpose="plant_photo",
        source=kwargs.pop("source", PNG_1PX),
        name=kwargs.pop("name", "photo.png"),
        accept=ACCEPT_IMAGES,
        **kwargs,
    )


# --- put + link round trip (the real bucket) -------------------------------


async def test_put_uploads_and_link_serves_the_bytes(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-roundtrip@example.com")
    stored = await _put_png(files, db_session, user.id)

    assert stored.content_type == "image/png"
    assert stored.byte_size == len(PNG_1PX)
    assert stored.name == "photo.png"
    assert stored.link_ttl_seconds == get_settings().files_default_link_ttl_seconds

    record = await db_session.get(FileRecord, stored.id)
    assert record is not None
    assert record.backend == "s3"
    assert record.bucket == get_settings().files_s3_bucket
    assert record.storage_key.startswith(f"{files.prefix}plants/plant_photo/")
    assert record.storage_key.endswith(f"{stored.id}.png")
    assert record.storage_key in await bucket_keys(files)

    link = await files.link(db_session, stored.id, domain="plants")
    async with httpx.AsyncClient() as http:
        response = await http.get(link.url)
    assert response.status_code == 200
    assert response.content == PNG_1PX
    assert response.headers["content-type"] == "image/png"
    # I6: a sniffed image is served inline, under its display name.
    assert response.headers["content-disposition"] == "inline; filename*=UTF-8''photo.png"


async def test_text_family_is_linked_as_attachment(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-html@example.com")
    upload = UploadFile(
        file=BytesIO(b"<script>alert(1)</script>"),
        filename="evil.html",
        headers=Headers({"content-type": "text/html"}),
    )
    stored = await files.put(
        db_session,
        owner=user.id,
        domain="learning",
        purpose="source",
        source=upload,
        name=upload.filename,
        accept=ACCEPT_DOCUMENTS,
    )
    assert stored.content_type == "text/html"

    link = await files.link(db_session, stored.id, domain="learning")
    async with httpx.AsyncClient() as http:
        response = await http.get(link.url)
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")


async def test_tampering_a_signed_response_override_breaks_the_link(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-tamper@example.com")
    stored = await _put_png(files, db_session, user.id)
    link = await files.link(db_session, stored.id, domain="plants")

    tampered = link.url.replace(
        "response-content-type=image%2Fpng", "response-content-type=text%2Fhtml"
    )
    assert tampered != link.url
    async with httpx.AsyncClient() as http:
        response = await http.get(tampered)
    assert response.status_code == 403


async def test_an_expired_link_is_refused_by_the_bucket(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-expired@example.com")
    stored = await _put_png(files, db_session, user.id)
    record = await db_session.get(FileRecord, stored.id)
    assert record is not None

    # Mint as if two hours ago with a one-minute TTL — no sleeping (§22.1).
    url, expires_at = files.backend.presign_get(
        record.bucket,
        record.storage_key,
        ttl=60,
        now=datetime.now(UTC) - timedelta(hours=2),
        content_type=record.content_type,
        content_disposition="inline",
    )
    assert expires_at < datetime.now(UTC)
    async with httpx.AsyncClient() as http:
        response = await http.get(url)
    assert response.status_code == 403


async def test_put_accepts_upload_file_and_async_iterator_sources(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-sources@example.com")
    from_upload = await _put_png(
        files, db_session, user.id, source=UploadFile(file=BytesIO(PNG_1PX), filename="a.png")
    )
    from_iterator = await _put_png(
        files, db_session, user.id, source=_chunks(PNG_1PX[:10], b"", PNG_1PX[10:])
    )
    assert from_upload.sha256 == from_iterator.sha256
    assert from_iterator.byte_size == len(PNG_1PX)


async def test_put_spools_large_uploads_to_disk_and_streams_them(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-large@example.com")
    # Past SPOOL_MAX_MEMORY (1 MiB), so the spool rolls over to a temp file.
    payload = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (3 * 1024 * 1024)
    stored = await files.put(
        db_session,
        owner=user.id,
        domain="learning",
        purpose="lecture",
        source=payload,
        accept=ACCEPT_VIDEOS,
    )
    assert stored.content_type == "video/mp4"
    assert stored.name == "file.mp4"
    link = await files.link(db_session, stored.id, domain="learning")
    async with httpx.AsyncClient() as http:
        response = await http.get(link.url)
    assert response.content == payload


# --- validation: nothing invalid ever reaches the bucket (§7.2) -------------


async def test_empty_upload_is_rejected(
    spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession
) -> None:
    files, spy = spy_files
    with pytest.raises(AppError) as exc_info:
        await _put_png(files, db_session, uuid4(), source=b"")
    assert exc_info.value.code == "core.files.empty_upload"
    assert spy.puts == []


async def test_oversized_upload_is_rejected_before_the_backend_sees_it(
    spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession
) -> None:
    files, spy = spy_files
    small = AcceptSpec(ACCEPT_IMAGES.content_types, 100)
    with pytest.raises(AppError) as exc_info:
        await files.put(
            db_session,
            owner=uuid4(),
            domain="plants",
            purpose="plant_photo",
            source=_chunks(PNG_1PX, b"\x00" * 200),
            accept=small,
        )
    assert exc_info.value.status_code == 413
    assert exc_info.value.code == "core.files.too_large"
    # The point of §7.2: a status code alone would pass a buffer-everything
    # implementation too.
    assert spy.puts == []


async def test_accept_spec_cannot_exceed_the_platform_ceiling(
    files_settings: Settings, spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession
) -> None:
    _, spy = spy_files
    tight = files_settings.model_copy(update={"files_max_bytes": 50})
    files = FileStore({"s3": spy}, active="s3", settings=tight)
    with pytest.raises(AppError) as exc_info:
        await _put_png(files, db_session, uuid4(), source=PNG_1PX + b"\x00" * 100)
    assert exc_info.value.code == "core.files.too_large"


async def test_svg_is_rejected_as_an_image(
    spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession
) -> None:
    files, spy = spy_files
    with pytest.raises(AppError) as exc_info:
        await _put_png(files, db_session, uuid4(), source=b"<svg xmlns='x'></svg>")
    assert exc_info.value.code == "core.files.unsupported_type"
    assert spy.puts == []


async def test_sniffed_type_outside_the_accept_spec_is_rejected(
    spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession
) -> None:
    files, _ = spy_files
    with pytest.raises(AppError) as exc_info:
        await files.put(
            db_session,
            owner=uuid4(),
            domain="plants",
            purpose="plant_photo",
            source=b"%PDF-1.7 not an image",
            accept=ACCEPT_IMAGES,
        )
    assert exc_info.value.code == "core.files.unsupported_type"


@pytest.mark.parametrize(
    "parts",
    [
        (b"hello \xff world",),  # invalid byte in the first chunk
        (b"hello ", b"\xc3\x28"),  # invalid sequence in a later chunk
        (b"truncated \xe2\x82",),  # multi-byte sequence cut off at the very end
    ],
)
async def test_text_family_requires_valid_utf8(
    spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession, parts: tuple[bytes, ...]
) -> None:
    files, spy = spy_files
    with pytest.raises(AppError) as exc_info:
        await files.put(
            db_session,
            owner=uuid4(),
            domain="learning",
            purpose="source",
            source=_chunks(*parts),
            accept=AcceptSpec(frozenset({"text/plain"}), 1024),
        )
    assert exc_info.value.code == "core.files.unsupported_type"
    assert spy.puts == []


async def test_ambiguous_text_without_a_declared_type_is_rejected(
    spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession
) -> None:
    files, _ = spy_files
    with pytest.raises(AppError) as exc_info:
        await files.put(
            db_session,
            owner=uuid4(),
            domain="learning",
            purpose="source",
            source=b"# heading",
            accept=ACCEPT_DOCUMENTS,  # four text types: bytes alone can't pick one
        )
    assert exc_info.value.code == "core.files.unsupported_type"


async def test_storage_failure_is_a_503_and_adds_no_row(
    files_settings: Settings, db_session: AsyncSession
) -> None:
    files = FileStore({"s3": SpyBackend(fail_put=True)}, active="s3", settings=files_settings)
    with pytest.raises(AppError) as exc_info:
        await _put_png(files, db_session, uuid4())
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "core.files.storage_unavailable"
    assert not [obj for obj in db_session.new if isinstance(obj, FileRecord)]


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\photo.png", "photo.png"),
        ("bad\nname\x00.png", "badname.png"),
        ("..", "file.png"),
        ("   ", "file.png"),
        (None, "file.png"),
        ("x" * 300 + ".png", "x" * 255),
    ],
)
async def test_names_are_sanitised(
    spy_files: tuple[FileStore, SpyBackend],
    db_session: AsyncSession,
    given: str | None,
    expected: str,
) -> None:
    files, _ = spy_files
    stored = await _put_png(files, db_session, uuid4(), name=given)
    assert stored.name == expected


# --- link TTL policy (§9.1) -------------------------------------------------


@pytest.mark.parametrize("ttl", [timedelta(seconds=59), timedelta(days=8)])
async def test_link_ttl_outside_sigv4_bounds_is_a_programming_error(
    spy_files: tuple[FileStore, SpyBackend], db_session: AsyncSession, ttl: timedelta
) -> None:
    files, spy = spy_files
    with pytest.raises(ValueError, match="link_ttl"):
        await _put_png(files, db_session, uuid4(), link_ttl=ttl)
    assert spy.puts == []


async def test_reader_may_shorten_but_never_extend_the_ttl(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-ttl@example.com")
    stored = await _put_png(files, db_session, user.id, link_ttl=timedelta(hours=1))
    assert stored.link_ttl_seconds == 3600

    before = datetime.now(UTC)
    default = await files.link(db_session, stored.id, domain="plants")
    shorter = await files.link(db_session, stored.id, domain="plants", max_ttl=timedelta(minutes=5))
    longer = await files.link(db_session, stored.id, domain="plants", max_ttl=timedelta(days=7))

    assert "X-Amz-Expires=3600" in default.url
    assert "X-Amz-Expires=300" in shorter.url
    assert "X-Amz-Expires=3600" in longer.url  # capped at the file's ceiling
    # Bucketed signing never lets a link outlive its TTL (§9.2).
    assert default.expires_at <= before + timedelta(hours=1) + timedelta(seconds=1)
    assert shorter.expires_at <= before + timedelta(minutes=5) + timedelta(seconds=1)

    with pytest.raises(ValueError, match="max_ttl"):
        await files.link(db_session, stored.id, domain="plants", max_ttl=timedelta(0))


async def test_links_are_stable_within_the_window(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-stable@example.com")
    stored = await _put_png(files, db_session, user.id, link_ttl=timedelta(days=7))
    first = await files.link(db_session, stored.id, domain="plants")
    second = await files.link(db_session, stored.id, domain="plants")
    assert first == second


# --- domain scoping (§7) ----------------------------------------------------


async def test_another_domain_cannot_read_link_or_delete_a_file(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-domain@example.com")
    stored = await _put_png(files, db_session, user.id, domain="plants")

    assert await files.get(db_session, stored.id, domain="learning") is None
    with pytest.raises(AppError) as exc_info:
        await files.link(db_session, stored.id, domain="learning")
    assert exc_info.value.code == "core.files.not_found"
    assert await files.links(db_session, [stored.id], domain="learning") == {}

    await files.delete(db_session, stored.id, domain="learning")
    record = await db_session.get(FileRecord, stored.id)
    assert record is not None and record.deleted_at is None

    got = await files.get(db_session, stored.id, domain="plants")
    assert got is not None and got.id == stored.id


async def test_unknown_and_deleted_files_are_not_found(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-gone@example.com")
    stored = await _put_png(files, db_session, user.id)
    await files.delete(db_session, stored.id, domain="plants")
    await files.delete(db_session, stored.id, domain="plants")  # idempotent
    await files.delete(db_session, uuid4(), domain="plants")  # unknown: no-op

    for file_id in (stored.id, uuid4()):
        assert await files.get(db_session, file_id, domain="plants") is None
        with pytest.raises(AppError) as exc_info:
            await files.link(db_session, file_id, domain="plants")
        assert exc_info.value.status_code == 404


async def test_links_batches_into_one_query_and_skips_missing_ids(
    files: FileStore, db_session: AsyncSession
) -> None:
    user = await make_user(db_session, email="files-batch@example.com")
    a = await _put_png(files, db_session, user.id)
    b = await _put_png(files, db_session, user.id)
    await db_session.flush()

    statements: list[str] = []

    def _count(orm_execute_state: Any) -> None:
        statements.append(str(orm_execute_state.statement))

    event.listen(db_session.sync_session, "do_orm_execute", _count)
    try:
        result = await files.links(db_session, [a.id, b.id, None, uuid4()], domain="plants")
    finally:
        event.remove(db_session.sync_session, "do_orm_execute", _count)

    assert set(result) == {a.id, b.id}
    assert len(statements) == 1
    assert await files.links(db_session, [None], domain="plants") == {}


# --- usage + settings -------------------------------------------------------


async def test_usage_totals_live_files(files: FileStore, db_session: AsyncSession) -> None:
    user = await make_user(db_session, email="files-usage@example.com")
    await _put_png(files, db_session, user.id)
    gone = await _put_png(files, db_session, user.id)
    await files.delete(db_session, gone.id, domain="plants")

    summary = await files.usage(db_session, owner=user.id, domain="plants")
    assert summary.total_count == 1
    assert summary.total_bytes == len(PNG_1PX)
    assert summary.rows[0].purpose == "plant_photo"


def test_settings_refuse_to_boot_without_a_bucket() -> None:
    with pytest.raises(ValidationError, match="DISP_FILES_S3_BUCKET"):
        Settings(files_s3_bucket="")  # type: ignore[call-arg]


def test_a_row_on_an_unregistered_backend_fails_loudly(files: FileStore) -> None:
    with pytest.raises(RuntimeError, match="no storage backend registered"):
        files.backend_for("gcs")
