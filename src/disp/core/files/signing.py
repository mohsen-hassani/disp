"""HMAC-signed, bucketed-expiry URLs for the core file/asset service.

See docs/milestones/server/M18-files.md §9. A signed URL is a capability, not a
session — anyone holding it gets the bytes until `exp`. The signature does
NOT bind a user id (§9.3): there is no cookie on an `<img>` request to check
it against, which is the entire reason this mechanism exists.
"""

import hashlib
import hmac
import math
import uuid
from base64 import urlsafe_b64encode
from datetime import datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HKDF_SALT = b"disp-file-url"
_HKDF_INFO = b"v1"
_HKDF_LENGTH = 32


def derive_key(jwt_secret: str) -> bytes:
    """Derive the file-URL signing key from DISP_JWT_SECRET (§9.2).

    Deriving rather than requiring a new env var means existing deployments
    need no new configuration, and the domain separation (distinct salt/info)
    guarantees a file signature can never be replayed as a session token or
    vice versa. Rotating DISP_JWT_SECRET invalidates outstanding file URLs
    exactly as it invalidates sessions.
    """
    return HKDF(
        algorithm=hashes.SHA256(), length=_HKDF_LENGTH, salt=_HKDF_SALT, info=_HKDF_INFO
    ).derive(jwt_secret.encode("utf-8"))


def bucket_expiry(now: datetime, ttl: int) -> int:
    """Round `now` up to the next `ttl`-second boundary (§9.1).

    A naive "now + ttl" expiry makes every mint of the same URL different, so
    every 30s query refetch produces a fresh URL/cache-key/re-download.
    Bucketing makes the URL byte-identical within a window so the browser
    cache actually hits. Real lifetime varies between 0 and ttl as a result —
    that's why files_url_ttl_seconds has a ge=60 floor.
    """
    return math.ceil(now.timestamp() / ttl) * ttl


def sign(asset_id: uuid.UUID, exp: int, *, key: bytes) -> str:
    message = f"v1:{asset_id}:{exp}".encode("ascii")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify(asset_id: uuid.UUID, exp: int, sig: str, *, key: bytes) -> bool:
    """Constant-time verification. Never raises — a garbled `sig` from a
    tampered query string must fail closed, not 500.

    Compares the base64-encoded signatures directly rather than decoding
    `sig` first: base64 encoding is injective, so encoded-string comparison
    is equivalent to comparing the raw digests, and it sidesteps needing a
    separate malformed-base64 code path entirely.
    """
    expected = sign(asset_id, exp, key=key)
    try:
        return hmac.compare_digest(expected, sig)
    except TypeError:
        return False


def build_url(asset_id: uuid.UUID, *, key: bytes, ttl: int, now: datetime) -> str:
    """Relative URL only (§9.1) — DISP_BASE_URL isn't the serving origin
    under `pnpm dev`/`preview`/e2e, and an absolute URL would be cross-origin
    against `img-src 'self'`.
    """
    exp = bucket_expiry(now, ttl)
    sig = sign(asset_id, exp, key=key)
    return f"/api/files/{asset_id}?exp={exp}&sig={sig}"
