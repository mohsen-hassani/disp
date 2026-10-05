"""S3Backend against MinIO (M18-files.md §6)."""

from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest

from disp.core.config import Settings
from disp.core.files.backends import StorageError
from disp.core.files.backends.s3 import S3Backend


@pytest.fixture
def backend(files_settings: Settings) -> S3Backend:
    return S3Backend.from_settings(files_settings)


async def test_put_list_delete_round_trip(backend: S3Backend, files_settings: Settings) -> None:
    prefix = files_settings.files_s3_prefix
    key = f"{prefix}a/{uuid4()}.bin"
    await backend.put(key, BytesIO(b"hello"), size=5, content_type="application/octet-stream")

    listed = [(k, modified) async for k, modified in backend.iter_objects(prefix)]
    assert [k for k, _ in listed] == [key]
    assert listed[0][1].tzinfo is not None

    await backend.delete(backend.bucket, key)
    await backend.delete(backend.bucket, key)  # idempotent: S3 answers 204 either way
    assert [k async for k, _ in backend.iter_objects(prefix)] == []


async def test_failures_surface_as_storage_errors(files_settings: Settings) -> None:
    broken = S3Backend.from_settings(
        files_settings.model_copy(update={"files_s3_bucket": f"no-such-bucket-{uuid4().hex[:8]}"})
    )
    with pytest.raises(StorageError):
        await broken.put("k", BytesIO(b"x"), size=1, content_type="text/plain")
    with pytest.raises(StorageError):
        await broken.delete(broken.bucket, "k")
    with pytest.raises(StorageError):
        _ = [k async for k, _ in broken.iter_objects("")]


def test_links_name_the_public_endpoint(files_settings: Settings) -> None:
    backend = S3Backend.from_settings(
        files_settings.model_copy(
            update={
                "files_s3_endpoint_url": "http://minio:9000",
                "files_s3_public_endpoint_url": "http://localhost:9000",
            }
        )
    )
    url, _ = backend.presign_get(
        "b",
        "k.png",
        ttl=60,
        now=datetime.now(UTC),
        content_type="image/png",
        content_disposition="inline",
    )
    assert url.startswith("http://localhost:9000/b/k.png?")


def test_aws_is_the_default_endpoint(files_settings: Settings) -> None:
    backend = S3Backend.from_settings(
        files_settings.model_copy(
            update={
                "files_s3_endpoint_url": None,
                "files_s3_public_endpoint_url": None,
                "files_s3_force_path_style": False,
            }
        )
    )
    url, _ = backend.presign_get(
        "b",
        "k.png",
        ttl=60,
        now=datetime.now(UTC),
        content_type="image/png",
        content_disposition="inline",
    )
    assert url.startswith("https://b.s3.amazonaws.com/k.png?")
