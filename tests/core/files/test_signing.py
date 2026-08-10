"""HMAC-signed, bucketed-expiry URLs (M18-files.md §9.2)."""

import uuid
from datetime import UTC, datetime

from disp.core.files import signing

KEY = signing.derive_key("a" * 40)
OTHER_KEY = signing.derive_key("b" * 40)


def test_valid_signature_verifies() -> None:
    asset_id = uuid.uuid4()
    sig = signing.sign(asset_id, 1000, key=KEY)
    assert signing.verify(asset_id, 1000, sig, key=KEY)


def test_tampered_asset_id_fails() -> None:
    asset_id = uuid.uuid4()
    other_id = uuid.uuid4()
    sig = signing.sign(asset_id, 1000, key=KEY)
    assert not signing.verify(other_id, 1000, sig, key=KEY)


def test_tampered_expiry_fails() -> None:
    asset_id = uuid.uuid4()
    sig = signing.sign(asset_id, 1000, key=KEY)
    assert not signing.verify(asset_id, 1001, sig, key=KEY)


def test_truncated_signature_fails() -> None:
    asset_id = uuid.uuid4()
    sig = signing.sign(asset_id, 1000, key=KEY)
    assert not signing.verify(asset_id, 1000, sig[:-4], key=KEY)


def test_signature_differing_in_last_byte_is_rejected() -> None:
    # Behavioral proxy for "verification uses hmac.compare_digest": a
    # near-miss signature must be rejected just as completely as a wildly
    # wrong one.
    asset_id = uuid.uuid4()
    sig = signing.sign(asset_id, 1000, key=KEY)
    tampered = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    assert not signing.verify(asset_id, 1000, tampered, key=KEY)


def test_foreign_key_signature_fails() -> None:
    asset_id = uuid.uuid4()
    sig = signing.sign(asset_id, 1000, key=OTHER_KEY)
    assert not signing.verify(asset_id, 1000, sig, key=KEY)


def test_valid_signature_at_a_past_expiry_still_verifies() -> None:
    # signing.verify checks the HMAC only; the `exp < now` gate is a separate
    # layer (FileStore.verify_signature). This pins that division so the two
    # concerns don't get accidentally merged later.
    asset_id = uuid.uuid4()
    sig = signing.sign(asset_id, 1000, key=KEY)
    assert signing.verify(asset_id, 1000, sig, key=KEY)


def test_garbled_signature_does_not_raise() -> None:
    asset_id = uuid.uuid4()
    assert not signing.verify(asset_id, 1000, "\x00not-base64!!", key=KEY)


def test_bucketing_two_mints_in_one_window_are_identical() -> None:
    now1 = datetime(2026, 8, 10, 12, 3, 17, tzinfo=UTC)
    now2 = datetime(2026, 8, 10, 12, 41, 2, tzinfo=UTC)
    assert signing.bucket_expiry(now1, 3600) == signing.bucket_expiry(now2, 3600)


def test_bucketing_crosses_into_the_next_bucket() -> None:
    now1 = datetime(2026, 8, 10, 12, 59, 59, tzinfo=UTC)
    now2 = datetime(2026, 8, 10, 13, 0, 1, tzinfo=UTC)
    assert signing.bucket_expiry(now1, 3600) != signing.bucket_expiry(now2, 3600)


def test_build_url_is_relative_and_carries_exp_and_sig() -> None:
    asset_id = uuid.uuid4()
    now = datetime(2026, 8, 10, 12, 3, 17, tzinfo=UTC)
    url = signing.build_url(asset_id, key=KEY, ttl=3600, now=now)
    assert url.startswith(f"/api/files/{asset_id}?exp=")
    assert "&sig=" in url


def test_verify_with_a_non_ascii_signature_does_not_raise() -> None:
    # hmac.compare_digest raises TypeError comparing strings with non-ASCII
    # characters — verify() must still fail closed, not 500, on a query
    # string a client could set to anything.
    asset_id = uuid.uuid4()
    assert not signing.verify(asset_id, 1000, "☃not-ascii", key=KEY)
