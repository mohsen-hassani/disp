from disp.core.contract import TileContext, TileData, TileItem
from disp.modules.plants import service

TILE_ITEMS_LIMIT = 5


def describe_lateness(days_overdue: int) -> str:
    """How a single due action reads on the tile."""
    if days_overdue <= 0:
        return "due today"
    if days_overdue == 1:
        return "1 day behind"
    return f"{days_overdue} days behind"


async def plants_due_tile(ctx: TileContext) -> TileData:
    """What needs doing right now.

    Everything here is derived from each interval's `next_due_on` at render
    time rather than read from a stored "notification" row, so the count is
    correct the instant an action is marked done and can never go stale.
    """
    summary = await service.due_summary(ctx.session, ctx.user)

    items = [
        TileItem(
            id=str(item.interval_id),
            primary=f"{item.action_name} — {item.plant_name}",
            secondary=describe_lateness(item.days_overdue),
            href=f"/api/plants/{item.plant_id}",
        )
        for item in summary.items[:TILE_ITEMS_LIMIT]
    ]

    return TileData(
        key="plants.due",
        title="Plant care",
        count=summary.count,
        items=items,
        empty_text="Nothing due today",
        generated_at=ctx.now,
    )
