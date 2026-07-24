from datetime import UTC, datetime
from uuid import uuid4

import pytest

from disp.core.errors import AppError
from disp.core.pagination import decode_cursor, encode_cursor


def test_cursor_round_trip() -> None:
    ts = datetime(2026, 7, 24, 9, 15, 0, tzinfo=UTC)
    note_id = uuid4()

    cursor = encode_cursor(ts, note_id)
    decoded = decode_cursor(cursor)

    assert decoded.ts == ts
    assert decoded.id == str(note_id)


def test_decode_invalid_cursor_raises_app_error() -> None:
    with pytest.raises(AppError) as exc_info:
        decode_cursor("not-valid-base64!!!")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "pagination.invalid_cursor"


def test_decode_malformed_json_raises_app_error() -> None:
    import base64

    payload = base64.urlsafe_b64encode(b"not json").decode("ascii")

    with pytest.raises(AppError) as exc_info:
        decode_cursor(payload)

    assert exc_info.value.code == "pagination.invalid_cursor"
