"""S3-compatible StorageBackend — Cloudflare R2 in production, MinIO in dev
and tests (M18-files.md §6).

The only module in the codebase that imports aioboto3. One client per
operation: a long-lived client binds to the event loop that created it, and
this code runs in the API, the worker, the CLI (`asyncio.run` per command)
and tests. Links are presigned by core's own `sigv4` module, not boto, so
minting one needs no client at all.
"""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, BinaryIO

import aioboto3
from aiobotocore.config import AioConfig
from botocore.exceptions import BotoCoreError, ClientError

from disp.core.config import Settings
from disp.core.files import sigv4
from disp.core.files.backends import StorageError

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client

_AWS_ENDPOINT = "https://s3.amazonaws.com"


class S3Backend:
    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        public_endpoint_url: str | None,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        force_path_style: bool,
    ) -> None:
        self.bucket = bucket
        self._endpoint_url = endpoint_url
        # The host is part of the signature, so links must name the host the
        # *browser* reaches — not necessarily the one this process uses
        # (M18-files.md §9.2).
        self._public_endpoint_url = public_endpoint_url or endpoint_url or _AWS_ENDPOINT
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._force_path_style = force_path_style
        self._session = aioboto3.Session()
        self._config = AioConfig(
            s3={"addressing_style": "path" if force_path_style else "virtual"},
            # Newer botocore sends CRC checksums by default, which not every
            # S3-compatible store accepts.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            retries={"max_attempts": 3, "mode": "standard"},
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3Backend":
        return cls(
            bucket=settings.files_s3_bucket,
            endpoint_url=settings.files_s3_endpoint_url,
            public_endpoint_url=settings.files_s3_public_endpoint_url,
            region=settings.files_s3_region,
            access_key_id=settings.files_s3_access_key_id.get_secret_value(),
            secret_access_key=settings.files_s3_secret_access_key.get_secret_value(),
            force_path_style=settings.files_s3_force_path_style,
        )

    def _client(self) -> "S3Client":
        return self._session.client(  # type: ignore[return-value]
            "s3",
            endpoint_url=self._endpoint_url,
            region_name=self._region,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            config=self._config,
        )

    async def put(self, key: str, body: BinaryIO, *, size: int, content_type: str) -> None:
        # One PutObject, never multipart: every accepted file is far below the
        # 5 GiB single-PUT limit, and a multipart upload that dies half-way is
        # billed as stored bytes until a lifecycle rule aborts it.
        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=body,
                    ContentLength=size,
                    ContentType=content_type,
                )
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"put {key!r} failed") from exc

    async def delete(self, bucket: str, key: str) -> None:
        # S3 answers DeleteObject with 204 whether or not the key exists, so
        # this is idempotent — purges and sweeps may race freely.
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"delete {key!r} failed") from exc

    async def iter_objects(self, prefix: str) -> AsyncIterator[tuple[str, datetime]]:
        try:
            async with self._client() as s3:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        yield obj["Key"], obj["LastModified"]
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"listing {prefix!r} failed") from exc

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
        signed_at = sigv4.bucketed_signing_time(now, ttl)
        url = sigv4.presign_get_url(
            endpoint=self._public_endpoint_url,
            bucket=bucket,
            key=key,
            region=self._region,
            access_key_id=self._access_key_id,
            secret_access_key=self._secret_access_key,
            expires_in=ttl,
            signed_at=signed_at,
            force_path_style=self._force_path_style,
            response_params={
                "response-content-disposition": content_disposition,
                "response-content-type": content_type,
            },
        )
        return url, signed_at + timedelta(seconds=ttl)
