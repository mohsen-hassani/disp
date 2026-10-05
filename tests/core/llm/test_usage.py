"""usage.py — write_call()/summarize() against core.llm_call (M19-llm.md
§6)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.llm.usage import summarize, write_call
from disp.core.models import LLMCallRow


async def test_write_call_inserts_row(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    user_id = uuid4()
    await write_call(
        session_maker,
        user_id=user_id,
        call_name="learning.grade_quiz",
        model="claude-opus-5",
        input_tokens=100,
        cached_read_tokens=20,
        output_tokens=50,
        latency_ms=1200,
        outcome="ok",
        error_code=None,
    )
    result = await db_session.execute(
        select(LLMCallRow).where(LLMCallRow.call_name == "learning.grade_quiz")
    )
    row = result.scalar_one()
    assert row.user_id == user_id
    assert row.input_tokens == 100
    assert row.outcome == "ok"


async def test_write_call_allows_null_user_id(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    await write_call(
        session_maker,
        user_id=None,
        call_name="learning.tag_generation",
        model="claude-haiku-4-5",
        input_tokens=1,
        cached_read_tokens=0,
        output_tokens=1,
        latency_ms=1,
        outcome="ok",
        error_code=None,
    )
    result = await db_session.execute(
        select(LLMCallRow).where(LLMCallRow.call_name == "learning.tag_generation")
    )
    row = result.scalar_one()
    assert row.user_id is None


async def test_write_call_rejects_invalid_outcome(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(DBAPIError):
        await write_call(
            session_maker,
            user_id=None,
            call_name="learning.bad",
            model="claude-opus-5",
            input_tokens=0,
            cached_read_tokens=0,
            output_tokens=0,
            latency_ms=0,
            outcome="not_a_real_outcome",
            error_code=None,
        )


async def test_summarize_groups_by_call_name_day_outcome(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    for _ in range(2):
        await write_call(
            session_maker,
            user_id=None,
            call_name="learning.explain",
            model="claude-opus-5",
            input_tokens=10,
            cached_read_tokens=0,
            output_tokens=5,
            latency_ms=1,
            outcome="ok",
            error_code=None,
        )
    await write_call(
        session_maker,
        user_id=None,
        call_name="learning.explain",
        model="claude-opus-5",
        input_tokens=10,
        cached_read_tokens=0,
        output_tokens=0,
        latency_ms=1,
        outcome="refused",
        error_code="core.llm.refused",
    )

    summary = await summarize(db_session, call_name="learning.explain")

    ok_rows = [r for r in summary.rows if r.outcome == "ok"]
    refused_rows = [r for r in summary.rows if r.outcome == "refused"]
    assert ok_rows and ok_rows[0].call_count == 2
    assert refused_rows and refused_rows[0].call_count == 1
    assert summary.total_calls == 3
    assert summary.total_input_tokens == 30


async def test_summarize_filters_by_since(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    await write_call(
        session_maker,
        user_id=None,
        call_name="learning.old_call",
        model="claude-opus-5",
        input_tokens=1,
        cached_read_tokens=0,
        output_tokens=1,
        latency_ms=1,
        outcome="ok",
        error_code=None,
    )
    future = datetime.now(UTC) + timedelta(days=1)
    summary = await summarize(db_session, since=future, call_name="learning.old_call")
    assert summary.rows == []
