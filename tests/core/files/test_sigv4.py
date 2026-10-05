"""Core's own SigV4 presigner (M18-files.md §9.2). Pure — no bucket needed;
test_store.py proves the same URLs are accepted by a real S3 server."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from disp.core.files import sigv4

AWS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # noqa: S105 — AWS's published example


def _url(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "endpoint": "https://s3.amazonaws.com",
        "bucket": "examplebucket",
        "key": "test.txt",
        "region": "us-east-1",
        "access_key_id": AWS_KEY_ID,
        "secret_access_key": AWS_SECRET,
        "expires_in": 86400,
        "signed_at": datetime(2013, 5, 24, tzinfo=UTC),
        "force_path_style": False,
    }
    kwargs.update(overrides)
    return sigv4.presign_get_url(**kwargs)  # type: ignore[arg-type]


def test_matches_the_aws_published_known_answer_vector() -> None:
    # "Authenticating Requests: Using Query Parameters (AWS Signature Version
    # 4)", Amazon S3 API reference — the canonical presigned GET example.
    url = _url()
    assert url.startswith("https://examplebucket.s3.amazonaws.com/test.txt?")
    assert url.endswith(
        "&X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
    )


def test_path_style_puts_the_bucket_in_the_path_and_keeps_the_port() -> None:
    url = _url(endpoint="http://localhost:9000", force_path_style=True)
    parts = urlsplit(url)
    assert parts.netloc == "localhost:9000"
    assert parts.path == "/examplebucket/test.txt"


def test_keys_and_overrides_are_percent_encoded() -> None:
    url = _url(
        key="plants/a b/ü.png",
        response_params={"response-content-disposition": "inline; filename*=UTF-8''a%20b.png"},
    )
    parts = urlsplit(url)
    assert parts.path == "/plants/a%20b/%C3%BC.png"  # '/' kept in the path
    query = parse_qs(parts.query)
    assert query["response-content-disposition"] == ["inline; filename*=UTF-8''a%20b.png"]


def test_response_overrides_change_the_signature() -> None:
    plain = _url()
    with_override = _url(response_params={"response-content-type": "image/png"})
    assert plain.rsplit("=", 1)[1] != with_override.rsplit("=", 1)[1]


@pytest.mark.parametrize("expires_in", [0, sigv4.MAX_EXPIRES_SECONDS + 1])
def test_expiry_outside_sigv4_bounds_is_refused(expires_in: int) -> None:
    with pytest.raises(ValueError, match="expires_in"):
        _url(expires_in=expires_in)


@pytest.mark.parametrize(
    ("ttl", "window"),
    [(60, 6), (5, 1), (3600, 360), (604_800, 3600)],
)
def test_stability_window(ttl: int, window: int) -> None:
    assert sigv4.stability_window(ttl) == window


@pytest.mark.parametrize("ttl", [60, 3600, 604_800])
def test_bucketed_signing_time_is_stable_and_never_outlives_the_ttl(ttl: int) -> None:
    window = sigv4.stability_window(ttl)
    start = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)
    first = sigv4.bucketed_signing_time(start, ttl)
    # Same window → same signing time → byte-identical URL.
    assert sigv4.bucketed_signing_time(start + timedelta(seconds=window - 1), ttl) == first
    assert sigv4.bucketed_signing_time(start + timedelta(seconds=window), ttl) > first

    for offset in range(0, window * 3, max(1, window // 4)):
        now = start + timedelta(seconds=offset)
        signed_at = sigv4.bucketed_signing_time(now, ttl)
        remaining = (signed_at + timedelta(seconds=ttl) - now).total_seconds()
        assert ttl - window < remaining <= ttl
