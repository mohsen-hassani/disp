"""Usage accounting against core.llm_call (M19-llm.md §6).

write_call() opens its own session_scope() rather than touching a caller's
session, so a usage row survives even when the caller's own transaction is
about to roll back (L3) — the same commit-then-raise mechanism
notifier.py:_deliver_notification uses for notification_log.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.db import session_scope
from disp.core.models import LLMCallRow


@dataclass(frozen=True)
class UsageRow:
    call_name: str
    day: date
    outcome: str
    call_count: int
    input_tokens: int
    cached_read_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class UsageSummary:
    rows: list[UsageRow]
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int


async def write_call(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID | None,
    call_name: str,
    model: str,
    input_tokens: int,
    cached_read_tokens: int,
    output_tokens: int,
    latency_ms: int,
    outcome: str,
    error_code: str | None,
) -> None:
    async with session_scope(session_maker) as session:
        session.add(
            LLMCallRow(
                user_id=user_id,
                call_name=call_name,
                model=model,
                input_tokens=input_tokens,
                cached_read_tokens=cached_read_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                outcome=outcome,
                error_code=error_code,
            )
        )


async def summarize(
    session: AsyncSession,
    *,
    since: datetime | None = None,
    call_name: str | None = None,
) -> UsageSummary:
    day = func.date_trunc("day", LLMCallRow.created_at).label("day")
    stmt = (
        select(
            LLMCallRow.call_name,
            day,
            LLMCallRow.outcome,
            func.count().label("call_count"),
            func.coalesce(func.sum(LLMCallRow.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(LLMCallRow.cached_read_tokens), 0).label("cached_read_tokens"),
            func.coalesce(func.sum(LLMCallRow.output_tokens), 0).label("output_tokens"),
        )
        .group_by(LLMCallRow.call_name, day, LLMCallRow.outcome)
        .order_by(day.desc())
    )
    if since is not None:
        stmt = stmt.where(LLMCallRow.created_at >= since)
    if call_name is not None:
        stmt = stmt.where(LLMCallRow.call_name == call_name)

    result = await session.execute(stmt)
    rows = [
        UsageRow(
            call_name=row.call_name,
            day=row.day.date(),
            outcome=row.outcome,
            call_count=row.call_count,
            input_tokens=row.input_tokens,
            cached_read_tokens=row.cached_read_tokens,
            output_tokens=row.output_tokens,
        )
        for row in result
    ]
    return UsageSummary(
        rows=rows,
        total_calls=sum(r.call_count for r in rows),
        total_input_tokens=sum(r.input_tokens for r in rows),
        total_output_tokens=sum(r.output_tokens for r in rows),
    )
