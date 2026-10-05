"""core.translation_call accounting — write_call and summarize
(M22-translation.md §7)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.models import TranslationCallRow
from disp.core.translation.usage import CallRecord, summarize, write_call


def _record(**overrides: object) -> CallRecord:
    data: dict[str, object] = {
        "user_id": None,
        "backend": "fake",
        "operation": "translate",
        "source_lang": "EN",
        "target_lang": "DE",
        "text_count": 1,
        "char_count": 5,
        "latency_ms": 1,
        "outcome": "ok",
        "error_code": None,
    }
    data.update(overrides)
    return CallRecord(**data)  # type: ignore[arg-type]


async def test_write_call_persists_every_column(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = uuid.uuid4()
    await write_call(
        session_maker,
        _record(user_id=user_id, outcome="rejected", error_code="core.translation.rejected"),
    )

    async with session_maker() as session:
        row = (await session.execute(select(TranslationCallRow))).scalar_one()
    assert row.user_id == user_id
    assert row.backend == "fake"
    assert row.operation == "translate"
    assert row.source_lang == "EN"
    assert row.target_lang == "DE"
    assert row.outcome == "rejected"
    assert row.error_code == "core.translation.rejected"


async def test_summarize_groups_by_backend_operation_day_and_outcome(
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    await write_call(session_maker, _record())
    await write_call(session_maker, _record())
    await write_call(session_maker, _record(operation="detect", char_count=7, target_lang=None))
    await write_call(session_maker, _record(backend="deepl", char_count=3))

    summary = await summarize(db_session)

    assert summary.total_calls == 4
    assert summary.total_texts == 4
    assert summary.total_chars == 20
    # The two identical translate rows collapse into one grouped row.
    assert len(summary.rows) == 3


async def test_summarize_filters_by_backend(
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    await write_call(session_maker, _record())
    await write_call(session_maker, _record(backend="deepl", char_count=3))

    summary = await summarize(db_session, backend="deepl")

    assert summary.total_calls == 1
    assert summary.total_chars == 3


async def test_summarize_filters_by_since(
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    await write_call(session_maker, _record())
    old = datetime.now(UTC) - timedelta(days=30)
    async with session_maker() as session:
        await session.execute(update(TranslationCallRow).values(created_at=old))
        await session.commit()
    await write_call(session_maker, _record(char_count=9))

    summary = await summarize(db_session, since=datetime.now(UTC) - timedelta(days=1))

    assert summary.total_calls == 1
    assert summary.total_chars == 9


async def test_summarize_is_empty_when_nothing_was_recorded(db_session: AsyncSession) -> None:
    summary = await summarize(db_session)
    assert summary.rows == []
    assert summary.total_calls == 0
    assert summary.total_chars == 0
