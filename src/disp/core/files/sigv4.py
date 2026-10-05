"""AWS Signature V4 query-string presigning for S3 `GET` links.

See docs/milestones/server/M18-files.md §9.2. This is core's own pure
implementation rather than botocore's `generate_presigned_url` for one
reason: botocore always signs with "now", so every mint of the same file
produces a different URL, and a 30-second query refetch would hand the
`<img>` a new `src` (a fresh download and a billed bucket read) every time.
Here the signing time is *bucketed*, so a link is byte-identical within a
stability window and the browser cache actually hits.

No I/O, no client, no clock: `now` is always passed in.
"""

import hashlib
import hmac
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

MAX_EXPIRES_SECONDS = 604_800  # SigV4's hard cap: 7 days
MAX_STABILITY_WINDOW_SECONDS = 3600

_ALGORITHM = "AWS4-HMAC-SHA256"
_SERVICE = "s3"


def stability_window(ttl: int) -> int:
    """How long a minted link stays byte-identical: a tenth of its TTL,
    clamped to [1 s, 1 h]. Bounds the real lifetime to (ttl - window, ttl]."""
    return max(1, min(ttl // 10, MAX_STABILITY_WINDOW_SECONDS))


def bucketed_signing_time(now: datetime, ttl: int) -> datetime:
    """Round `now` DOWN to the stability window. Rounding down (not up) is
    what guarantees a link never outlives its TTL: it expires at
    signing_time + ttl <= now + ttl."""
    window = stability_window(ttl)
    seconds = int(now.timestamp()) // window * window
    return datetime.fromtimestamp(seconds, tz=UTC)


def _encode(value: str, *, keep_slash: bool) -> str:
    # SigV4 URI-encoding: everything except RFC 3986 unreserved characters
    # is percent-encoded, UTF-8 first; '/' survives only in the path.
    return quote(value, safe="-_.~/" if keep_slash else "-_.~")


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def presign_get_url(
    *,
    endpoint: str,
    bucket: str,
    key: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
    expires_in: int,
    signed_at: datetime,
    force_path_style: bool,
    response_params: Mapping[str, str] | None = None,
) -> str:
    """A presigned `GET` URL for `bucket`/`key`, valid from `signed_at` for
    `expires_in` seconds. `response_params` (e.g. `response-content-type`)
    are signed into the query, so the headers the bucket serves are the
    signer's decision, not the uploader's."""
    if not 1 <= expires_in <= MAX_EXPIRES_SECONDS:
        raise ValueError(f"expires_in must be within 1..{MAX_EXPIRES_SECONDS}, got {expires_in}")

    parts = urlsplit(endpoint)
    host = parts.netloc
    base_path = parts.path.rstrip("/")
    if force_path_style:
        path = f"{base_path}/{bucket}/{key}"
    else:
        host = f"{bucket}.{host}"
        path = f"{base_path}/{key}"
    canonical_uri = _encode(path, keep_slash=True)

    amz_date = signed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    datestamp = amz_date[:8]
    scope = f"{datestamp}/{region}/{_SERVICE}/aws4_request"

    params = {
        "X-Amz-Algorithm": _ALGORITHM,
        "X-Amz-Credential": f"{access_key_id}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires_in),
        "X-Amz-SignedHeaders": "host",
        **(response_params or {}),
    }
    canonical_query = "&".join(
        f"{_encode(name, keep_slash=False)}={_encode(value, keep_slash=False)}"
        for name, value in sorted(params.items())
    )

    canonical_request = "\n".join(
        ["GET", canonical_uri, canonical_query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"]
    )
    string_to_sign = "\n".join(
        [
            _ALGORITHM,
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    signing_key = _hmac(f"AWS4{secret_access_key}".encode(), datestamp)
    signing_key = _hmac(signing_key, region)
    signing_key = _hmac(signing_key, _SERVICE)
    signing_key = _hmac(signing_key, "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return f"{parts.scheme}://{host}{canonical_uri}?{canonical_query}&X-Amz-Signature={signature}"
