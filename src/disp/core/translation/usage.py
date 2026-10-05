"""Usage accounting against core.translation_call (M22-translation.md §7).

write_call()/write_call_sync() open their own session scope rather than
touching a caller's session, so a usage row survives even when the caller's
own transaction is about to roll back (T5) — the same commit-then-raise
mechanism notifier.py:_deliver_notification uses for notification_log and
llm/usage.py:write_call uses for core.llm_call.

The sync half exists because the sync facade must account for its calls too;
`sync_session_scope` (core/db.py) was added by this milestone for exactly
that, rather than driving the async path from a nested event loop (§5.1).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from disp.core.db import session_scope, sync_session_scope
from disp.core.models import TranslationCallRow


@dataclass(frozen=True)
class UsageRow:
    backend: str
    operation: str
    day: date
    outcome: str
    call_count: int
    text_count: int
    char_count: int


@dataclass(frozen=True)
class UsageSummary:
    rows: list[UsageRow]
    total_calls: int
    total_texts: int
    total_chars: int


@dataclass(frozen=True)
class CallRecord:
    """One row's worth of accounting, shared by the sync and async writers so
    the two cannot disagree about what a row contains."""

    user_id: uuid.UUID | None
    backend: str
    operation: str
    source_lang: str | None
    target_lang: str | None
    text_count: int
    char_count: int
    latency_ms: int
    outcome: str
    error_code: str | None


def _row(record: CallRecord) -> TranslationCallRow:
    return TranslationCallRow(
        user_id=record.user_id,
        backend=record.backend,
        operation=record.operation,
        source_lang=record.source_lang,
        target_lang=record.target_lang,
        text_count=record.text_count,
        char_count=record.char_count,
        latency_ms=record.latency_ms,
        outcome=record.outcome,
        error_code=record.error_code,
    )


async def write_call(
    session_maker: async_sessionmaker[AsyncSession] | None,
    record: CallRecord,
) -> None:
    async with session_scope(session_maker) as session:
        session.add(_row(record))


def write_call_sync(
    session_maker: sessionmaker[Session] | None,
    record: CallRecord,
) -> None:
    with sync_session_scope(session_maker) as session:
        session.add(_row(record))


async def summarize(
    session: AsyncSession,
    *,
    since: datetime | None = None,
    backend: str | None = None,
) -> UsageSummary:
    day = func.date_trunc("day", TranslationCallRow.created_at).label("day")
    stmt = (
        select(
            TranslationCallRow.backend,
            TranslationCallRow.operation,
            day,
            TranslationCallRow.outcome,
            func.count().label("call_count"),
            func.coalesce(func.sum(TranslationCallRow.text_count), 0).label("text_count"),
            func.coalesce(func.sum(TranslationCallRow.char_count), 0).label("char_count"),
        )
        .group_by(
            TranslationCallRow.backend,
            TranslationCallRow.operation,
            day,
            TranslationCallRow.outcome,
        )
        .order_by(day.desc())
    )
    if since is not None:
        stmt = stmt.where(TranslationCallRow.created_at >= since)
    if backend is not None:
        stmt = stmt.where(TranslationCallRow.backend == backend)

    result = await session.execute(stmt)
    rows = [
        UsageRow(
            backend=row.backend,
            operation=row.operation,
            day=row.day.date(),
            outcome=row.outcome,
            call_count=row.call_count,
            text_count=row.text_count,
            char_count=row.char_count,
        )
        for row in result
    ]
    return UsageSummary(
        rows=rows,
        total_calls=sum(r.call_count for r in rows),
        total_texts=sum(r.text_count for r in rows),
        total_chars=sum(r.char_count for r in rows),
    )
