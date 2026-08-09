import base64
import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from disp.core.errors import AppError


class CursorData(BaseModel):
    ts: datetime
    id: str


def encode_cursor(ts: datetime, id_: UUID | str) -> str:
    payload = json.dumps({"ts": ts.isoformat(), "id": str(id_)}).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decode_cursor(cursor: str) -> CursorData:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(payload)
        return CursorData(ts=data["ts"], id=data["id"])
    except Exception as exc:
        raise AppError(
            status_code=400,
            code="core.pagination.invalid_cursor",
            title="Invalid cursor",
            detail="The pagination cursor could not be decoded.",
        ) from exc


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None
    has_more: bool
