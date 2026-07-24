from uuid import UUID

from sqlalchemy import func, select

from disp.core.auth import readable_ids
from disp.core.contract import TileAction, TileContext, TileData, TileItem
from disp.modules.notes.models import Note
from disp.modules.notes.service import RESOURCE_TYPE

BODY_PREVIEW_LEN = 60
LATEST_ITEMS_LIMIT = 5

QUICK_ADD_ACTION = TileAction(
    id="quick_add",
    label="Add note",
    method="POST",
    path="/api/notes",
    body_schema={
        "type": "object",
        "required": ["body"],
        "properties": {"body": {"type": "string"}},
    },
)


def _preview(title: str | None, body: str) -> str:
    if title:
        return title
    if len(body) <= BODY_PREVIEW_LEN:
        return body
    return body[:BODY_PREVIEW_LEN] + "…"


async def notes_latest_tile(ctx: TileContext) -> TileData:
    ids = await readable_ids(ctx.session, user_id=ctx.user.id, resource_type=RESOURCE_TYPE)
    note_ids = [UUID(resource_id) for resource_id in ids]

    count = 0
    items: list[TileItem] = []

    if note_ids:
        count_result = await ctx.session.execute(
            select(func.count())
            .select_from(Note)
            .where(Note.id.in_(note_ids), Note.deleted_at.is_(None))
        )
        count = count_result.scalar_one()

        rows_result = await ctx.session.execute(
            select(Note)
            .where(Note.id.in_(note_ids), Note.deleted_at.is_(None))
            .order_by(Note.created_at.desc())
            .limit(LATEST_ITEMS_LIMIT)
        )
        items = [
            TileItem(
                id=str(note.id),
                primary=_preview(note.title, note.body),
                secondary="pinned" if note.pinned else None,
                timestamp=note.created_at,
                href=f"/api/notes/{note.id}",
            )
            for note in rows_result.scalars()
        ]

    return TileData(
        key="notes.latest",
        title="Latest notes",
        count=count,
        items=items,
        actions=[QUICK_ADD_ACTION],
        empty_text="No notes yet",
        generated_at=ctx.now,
    )
