"""FileStore.put/get/open/delete (M18-files.md §7, §8.1, §8.2)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import Headers

from disp.core.config import get_settings
from disp.core.errors import AppError
from disp.core.files import signing
from disp.core.files.backends.local import LocalBackend
from disp.core.files.store import ACCEPT_DOCUMENTS, ACCEPT_IMAGES, AcceptSpec, FileStore
from disp.core.files.sweep import run_sweep
from disp.core.models import Asset
from tests.factories import make_user

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


class _SpyBackend:
    name = "local"

    def __init__(self) -> None:
        self.write_called = False

    async def write(self, key: str, chunks: AsyncIterator[bytes]) -> None:
        self.write_called = True
        async for _chunk in chunks:
            pass

    async def read(self, key: str) -> AsyncIterator[bytes]:
        raise NotImplementedError
        yield b""  # pragma: no cover

    async def delete(self, key: str) -> None:
        return None

    async def exists(self, key: str) -> bool:
        return False

    async def iter_objects(self, prefix: str = "") -> AsyncIterator[tuple[str, datetime]]:
        return
        yield  # pragma: no cover

    def native_signed_url(self, key: str, *, content_type: str, expires_in: int) -> str | None:
        return None


async def _single_chunk(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


async def test_put_get_round_trip(db_session: AsyncSession, tmp_path: Path) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-roundtrip@example.com")
    await db_session.flush()

    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=_single_chunk(PNG_1PX),
        filename="photo.png",
        accept=ACCEPT_IMAGES,
    )
    await db_session.flush()

    assert stored.content_type == "image/png"
    assert stored.byte_size == len(PNG_1PX)
    assert stored.original_filename == "photo.png"

    fetched = await files.get(db_session, stored.id)
    assert fetched is not None
    assert fetched.sha256 == stored.sha256

    body = b""
    async for chunk in await files.open(db_session, stored.id):
        body += chunk
    assert body == PNG_1PX


async def test_put_ignores_declared_content_type_for_sniffable_bytes(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    # I5: what's served is decided by content, never a declared type. Here
    # nothing declares a type at all (raw bytes) — sniffing still identifies
    # it correctly from the magic bytes alone.
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-sniff@example.com")
    await db_session.flush()

    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=_single_chunk(PNG_1PX),
        accept=ACCEPT_IMAGES,
    )
    assert stored.content_type == "image/png"


async def test_empty_upload_is_rejected(db_session: AsyncSession, tmp_path: Path) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-empty@example.com")
    await db_session.flush()

    async def empty() -> AsyncIterator[bytes]:
        return
        yield b""  # pragma: no cover

    with pytest.raises(AppError) as exc:
        await files.put(
            db_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=empty(),
            accept=ACCEPT_IMAGES,
        )
    assert exc.value.code == "core.files.empty_upload"
    assert exc.value.status_code == 400


async def test_unsniffable_svg_is_rejected_at_the_accept_gate(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-svg@example.com")
    await db_session.flush()

    with pytest.raises(AppError) as exc:
        await files.put(
            db_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=_single_chunk(b"<?xml version='1.0'?><svg></svg>"),
            accept=ACCEPT_IMAGES,
        )
    assert exc.value.code == "core.files.unsupported_type"
    assert exc.value.status_code == 415


async def test_oversized_upload_never_reaches_backend_write(
    db_session: AsyncSession,
) -> None:
    spy = _SpyBackend()
    files = FileStore(spy, settings=get_settings())
    user = await make_user(db_session, email="files-store-oversize@example.com")
    await db_session.flush()

    accept = AcceptSpec(frozenset({"image/png"}), max_bytes=128)

    async def unbounded_source() -> AsyncIterator[bytes]:
        # Would run forever if fully consumed — the very first chunk alone
        # already exceeds max_bytes, so put() must never look past it, and
        # the spy backend's write() must never be invoked at all.
        while True:
            yield PNG_1PX + b"\x00" * 100_000

    with pytest.raises(AppError) as exc:
        await files.put(
            db_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=unbounded_source(),
            accept=accept,
        )

    assert exc.value.code == "core.files.too_large"
    assert exc.value.status_code == 413
    assert spy.write_called is False


async def test_open_distinguishes_missing_row_from_missing_object(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-missing@example.com")
    await db_session.flush()

    with pytest.raises(AppError) as unknown:
        await files.open(db_session, uuid4())
    assert unknown.value.code == "core.files.not_found"
    assert unknown.value.status_code == 404

    # A row whose object never made it to disk — the DB-only-restore case
    # (§15.3) — must be distinguishable from "never existed".
    asset = Asset(
        owner_user_id=user.id,
        domain="plants",
        purpose="plant_photo",
        content_type="image/png",
        byte_size=1,
        sha256="0" * 64,
        backend="local",
        storage_key="never/written.bin",
    )
    db_session.add(asset)
    await db_session.flush()

    with pytest.raises(AppError) as missing:
        await files.open(db_session, asset.id)
    assert missing.value.code == "core.files.missing_object"
    assert missing.value.status_code == 404


async def test_delete_soft_deletes_and_never_touches_bytes(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-delete@example.com")
    await db_session.flush()

    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=_single_chunk(PNG_1PX),
        accept=ACCEPT_IMAGES,
    )
    await db_session.flush()

    await files.delete(db_session, stored.id)
    await db_session.flush()

    assert await files.get(db_session, stored.id) is None
    row = (await db_session.execute(select(Asset).where(Asset.id == stored.id))).scalar_one()
    assert row.deleted_at is not None
    assert await files.backend.exists(row.storage_key)  # I2: bytes untouched

    await files.delete(db_session, stored.id)  # idempotent


async def test_delete_of_unknown_asset_is_a_silent_no_op(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    await files.delete(db_session, uuid4())


async def test_put_transaction_rollback_orphans_the_object_reaped_only_by_the_sweeper(
    tmp_path: Path,
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-txn@example.com")
    await db_session.flush()

    async with session_maker() as txn_session:
        stored = await files.put(
            txn_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=_single_chunk(PNG_1PX),
            accept=ACCEPT_IMAGES,
        )
        await txn_session.rollback()

    # I1's inverse: a rollback after put() leaves an object with no row.
    result = await db_session.execute(select(Asset).where(Asset.id == stored.id))
    assert result.scalar_one_or_none() is None

    keys = [key async for key, _ in files.backend.iter_objects() if str(stored.id) in key]
    assert len(keys) == 1

    grace = get_settings().files_sweep_grace_seconds
    future = datetime.now(UTC) + timedelta(seconds=grace + 3600)
    await run_sweep(db_session, backend=files.backend, grace_seconds=grace, now=future)

    keys_after = [key async for key, _ in files.backend.iter_objects() if str(stored.id) in key]
    assert keys_after == []


async def test_verify_signature_rejects_an_expired_bucket(tmp_path: Path) -> None:
    settings = get_settings()
    files = FileStore(LocalBackend(tmp_path), settings=settings)
    key = signing.derive_key(settings.jwt_secret.get_secret_value())
    asset_id = uuid4()
    past_exp = int(datetime.now(UTC).timestamp()) - 10
    sig = signing.sign(asset_id, past_exp, key=key)

    assert not files.verify_signature(asset_id, exp=past_exp, sig=sig)


async def test_verify_signature_accepts_a_valid_future_bucket(tmp_path: Path) -> None:
    settings = get_settings()
    files = FileStore(LocalBackend(tmp_path), settings=settings)
    key = signing.derive_key(settings.jwt_secret.get_secret_value())
    asset_id = uuid4()
    future_exp = int(datetime.now(UTC).timestamp()) + 3600
    sig = signing.sign(asset_id, future_exp, key=key)

    assert files.verify_signature(asset_id, exp=future_exp, sig=sig)


async def test_signed_url_is_stable_within_a_bucket(tmp_path: Path) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    asset_id = uuid4()
    assert files.signed_url(asset_id) == files.signed_url(asset_id)


def test_from_settings_raises_for_unimplemented_s3_backend() -> None:
    from pydantic import SecretStr

    s3_settings = get_settings().model_copy(
        update={
            "files_backend": "s3",
            "files_s3_bucket": "my-bucket",
            "files_s3_access_key_id": SecretStr("key"),
            "files_s3_secret_access_key": SecretStr("secret"),
        }
    )
    with pytest.raises(RuntimeError, match="S3 backend not yet implemented"):
        FileStore.from_settings(s3_settings)


async def test_put_accepts_raw_bytes_as_source(db_session: AsyncSession, tmp_path: Path) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-bytes-source@example.com")
    await db_session.flush()

    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=PNG_1PX,
        accept=ACCEPT_IMAGES,
    )
    assert stored.byte_size == len(PNG_1PX)


async def test_put_accepts_an_uploadfile_as_source(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-uploadfile@example.com")
    await db_session.flush()

    upload = UploadFile(file=BytesIO(PNG_1PX), filename="photo.png")
    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=upload,
        filename=upload.filename,
        accept=ACCEPT_IMAGES,
    )
    assert stored.byte_size == len(PNG_1PX)


async def test_sniffed_type_outside_accept_is_rejected(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-wrong-accept@example.com")
    await db_session.flush()

    with pytest.raises(AppError) as exc:
        await files.put(
            db_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=_single_chunk(PNG_1PX),
            accept=AcceptSpec(frozenset({"image/jpeg"}), 1000),
        )
    assert exc.value.code == "core.files.unsupported_type"


async def test_put_uses_uploadfiles_declared_type_for_text_family(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-text-declared@example.com")
    await db_session.flush()

    upload = UploadFile(
        file=BytesIO(b"# hello"),
        filename="notes.md",
        headers=Headers({"content-type": "text/markdown"}),
    )
    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=upload,
        filename=upload.filename,
        accept=ACCEPT_DOCUMENTS,
    )
    assert stored.content_type == "text/markdown"


async def test_text_family_first_chunk_invalid_utf8_is_rejected(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-bad-utf8@example.com")
    await db_session.flush()

    with pytest.raises(AppError) as exc:
        await files.put(
            db_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=_single_chunk(b"\xff\xfe not valid utf-8"),
            accept=AcceptSpec(frozenset({"text/plain"}), 1000),
        )
    assert exc.value.code == "core.files.unsupported_type"


async def test_multi_chunk_upload_streams_and_reassembles_correctly(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-multichunk@example.com")
    await db_session.flush()

    async def two_chunks() -> AsyncIterator[bytes]:
        yield PNG_1PX[:50]
        yield PNG_1PX[50:]

    stored = await files.put(
        db_session,
        owner=user.id,
        domain="plants",
        purpose="plant_photo",
        source=two_chunks(),
        accept=ACCEPT_IMAGES,
    )
    assert stored.byte_size == len(PNG_1PX)

    body = b""
    async for chunk in await files.open(db_session, stored.id):
        body += chunk
    assert body == PNG_1PX


async def test_oversized_upload_on_a_later_chunk_is_rejected_mid_stream(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-late-overflow@example.com")
    await db_session.flush()

    async def chunks() -> AsyncIterator[bytes]:
        yield PNG_1PX
        yield b"\x00" * 1000

    with pytest.raises(AppError) as exc:
        await files.put(
            db_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=chunks(),
            accept=AcceptSpec(frozenset({"image/png"}), max_bytes=len(PNG_1PX) + 10),
        )
    assert exc.value.code == "core.files.too_large"


async def test_text_family_later_chunk_invalid_utf8_is_rejected(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user = await make_user(db_session, email="files-store-late-bad-utf8@example.com")
    await db_session.flush()

    async def chunks() -> AsyncIterator[bytes]:
        yield b"hello "
        yield b"\xff\xfe bad"

    with pytest.raises(AppError) as exc:
        await files.put(
            db_session,
            owner=user.id,
            domain="plants",
            purpose="plant_photo",
            source=chunks(),
            accept=AcceptSpec(frozenset({"text/plain"}), 1000),
        )
    assert exc.value.code == "core.files.unsupported_type"


async def test_usage_filters_by_owner_and_domain(db_session: AsyncSession, tmp_path: Path) -> None:
    files = FileStore(LocalBackend(tmp_path), settings=get_settings())
    user_a = await make_user(db_session, email="files-usage-a@example.com")
    user_b = await make_user(db_session, email="files-usage-b@example.com")
    await db_session.flush()

    await files.put(
        db_session,
        owner=user_a.id,
        domain="plants",
        purpose="plant_photo",
        source=_single_chunk(PNG_1PX),
        accept=ACCEPT_IMAGES,
    )
    await files.put(
        db_session,
        owner=user_b.id,
        domain="plants",
        purpose="plant_photo",
        source=_single_chunk(PNG_1PX),
        accept=ACCEPT_IMAGES,
    )
    await db_session.flush()

    by_owner = await files.usage(db_session, owner=user_a.id)
    assert by_owner.total_count == 1

    by_domain = await files.usage(db_session, domain="plants")
    assert by_domain.total_count == 2

    by_missing_domain = await files.usage(db_session, domain="notes")
    assert by_missing_domain.total_count == 0
