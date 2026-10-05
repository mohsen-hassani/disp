"""LLMFacade.generate()/generate_text() — invariants L1, L3, L5, L6, decision
2 (LLMNotConfigured writes no row), decision 3 (count_tokens is exempt from
the "no network before budget check" rule) (M19-llm.md §4, §6, §12).

Uses a hand-rolled stub in place of the real anthropic client (no network,
ever) but a REAL Postgres session via the `session_maker` fixture, so L3's
"the row survives even when the caller's transaction rolls back" is actually
proven against the database, not simulated.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import Settings, get_settings
from disp.core.llm import LLMCall, LLMFacade
from disp.core.llm.errors import (
    LLMInputTooLarge,
    LLMInvalidOutput,
    LLMNotConfigured,
    LLMRefused,
)
from disp.core.models import LLMCallRow


class _Alignment(BaseModel):
    topics: list[str]


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _StubMessages:
    def __init__(self, *, create_results: list[object], count_tokens_input_tokens: int) -> None:
        self._create_results = list(create_results)
        self._count_tokens_input_tokens = count_tokens_input_tokens
        self.create_calls: list[dict[str, object]] = []
        self.count_tokens_calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.create_calls.append(kwargs)
        result = self._create_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def count_tokens(self, **kwargs: object) -> object:
        self.count_tokens_calls.append(kwargs)
        return SimpleNamespace(input_tokens=self._count_tokens_input_tokens)


class _StubClient:
    def __init__(
        self, *, create_results: list[object], count_tokens_input_tokens: int = 10
    ) -> None:
        self.messages = _StubMessages(
            create_results=create_results, count_tokens_input_tokens=count_tokens_input_tokens
        )


def _response(text: str) -> object:
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[_TextBlock(text)],
        stop_details=None,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0),
    )


def _refusal_response(category: str) -> object:
    return SimpleNamespace(
        stop_reason="refusal",
        content=[],
        stop_details=SimpleNamespace(category=category),
        usage=SimpleNamespace(input_tokens=10, output_tokens=0, cache_read_input_tokens=0),
    )


def _enabled_settings(**overrides: object) -> Settings:
    base = get_settings()
    data = base.model_dump()
    data.update(llm_enabled=True, llm_api_key=SecretStr("sk-test"))
    data.update(overrides)
    return Settings(**data)


def _facade(
    session_maker: async_sessionmaker[AsyncSession], stub: _StubClient, **settings_overrides: object
) -> LLMFacade:
    settings = _enabled_settings(**settings_overrides)
    facade = LLMFacade.from_settings(settings, session_maker)
    facade._client = stub  # type: ignore[attr-defined]
    return facade


async def _call_rows(session: AsyncSession, call_name: str) -> list[LLMCallRow]:
    result = await session.execute(
        select(LLMCallRow).where(LLMCallRow.call_name == call_name).order_by(LLMCallRow.created_at)
    )
    return list(result.scalars())


async def test_generate_returns_validated_instance(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    stub = _StubClient(create_results=[_response('{"topics": ["a", "b"]}')])
    facade = _facade(session_maker, stub)
    call = LLMCall(
        name="learning.align_topics", schema=_Alignment, system="s", max_output_tokens=100
    )

    result = await facade.generate(call, "content", user_id=None)

    assert isinstance(result, _Alignment)
    assert result.topics == ["a", "b"]
    rows = await _call_rows(db_session, "learning.align_topics")
    assert len(rows) == 1
    assert rows[0].outcome == "ok"


async def test_generate_repairs_once_then_succeeds(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    stub = _StubClient(
        create_results=[_response("not json at all"), _response('{"topics": ["fixed"]}')]
    )
    facade = _facade(session_maker, stub)
    call = LLMCall(
        name="learning.align_topics", schema=_Alignment, system="s", max_output_tokens=100
    )

    result = await facade.generate(call, "content", user_id=None)

    assert result.topics == ["fixed"]
    assert len(stub.messages.create_calls) == 2
    rows = await _call_rows(db_session, "learning.align_topics")
    assert len(rows) == 1
    assert rows[0].outcome == "ok"


async def test_generate_raises_invalid_output_after_second_failure(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    stub = _StubClient(create_results=[_response("nope"), _response("still nope")])
    facade = _facade(session_maker, stub)
    call = LLMCall(
        name="learning.align_topics", schema=_Alignment, system="s", max_output_tokens=100
    )

    with pytest.raises(LLMInvalidOutput):
        await facade.generate(call, "content", user_id=None)

    assert len(stub.messages.create_calls) == 2
    rows = await _call_rows(db_session, "learning.align_topics")
    assert len(rows) == 1
    assert rows[0].outcome == "invalid_output"


async def test_generate_writes_row_even_when_caller_transaction_rolls_back(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    """L3, proven from a SEPARATE session against a real database — asserting
    inside the caller's own (about to roll back) transaction proves nothing."""
    stub = _StubClient(create_results=[_response("invalid"), _response("still invalid")])
    facade = _facade(session_maker, stub)
    call = LLMCall(name="learning.grade", schema=_Alignment, system="s", max_output_tokens=100)

    with pytest.raises(LLMInvalidOutput):
        await facade.generate(call, "content", user_id=None)

    # A fresh session against the same (savepoint-scoped) connection — the
    # row was committed by write_call()'s own session_scope, independent of
    # whatever the caller does next.
    async with session_maker() as fresh_session:
        rows = await _call_rows(fresh_session, "learning.grade")
    assert len(rows) == 1
    assert rows[0].outcome == "invalid_output"


async def test_generate_input_too_large_raises_before_generation_request(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    """L5 (decision 3): count_tokens() is allowed to hit the stub, but
    messages.create() must never be called once the budget is exceeded."""
    stub = _StubClient(create_results=[], count_tokens_input_tokens=999_999)
    facade = _facade(session_maker, stub)
    call = LLMCall(
        name="learning.summarize",
        schema=_Alignment,
        system="s",
        max_output_tokens=100,
        max_input_tokens=100,
    )

    with pytest.raises(LLMInputTooLarge):
        await facade.generate(call, "content", user_id=None)

    assert len(stub.messages.count_tokens_calls) == 1
    assert len(stub.messages.create_calls) == 0
    rows = await _call_rows(db_session, "learning.summarize")
    assert len(rows) == 1
    assert rows[0].outcome == "too_large"
    assert rows[0].input_tokens == 999_999


async def test_generate_not_configured_writes_no_row(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    """Decision 2: a config-gate rejection is not a 'call' — no row at all."""
    settings = _enabled_settings(llm_enabled=False, llm_api_key=SecretStr(""))
    facade = LLMFacade.from_settings(settings, session_maker)
    call = LLMCall(name="learning.explain", schema=_Alignment, system="s", max_output_tokens=100)

    with pytest.raises(LLMNotConfigured):
        await facade.generate(call, "content", user_id=None)

    rows = await _call_rows(db_session, "learning.explain")
    assert rows == []


async def test_generate_text_returns_raw_text(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    stub = _StubClient(create_results=[_response("a free-form reply")])
    facade = _facade(session_maker, stub)
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=100)

    text = await facade.generate_text(call, "hi", user_id=uuid4())

    assert text == "a free-form reply"
    rows = await _call_rows(db_session, "learning.chat")
    assert len(rows) == 1
    assert rows[0].outcome == "ok"
    assert rows[0].user_id is not None


async def test_generate_rejects_schema_none() -> None:
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=100)
    settings = _enabled_settings()
    # ValueError is raised before session_maker is ever touched.
    facade = LLMFacade.from_settings(settings, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="schema"):
        await facade.generate(call, "content")


async def test_generate_text_rejects_schema_set() -> None:
    call = LLMCall(name="learning.chat", schema=_Alignment, system="s", max_output_tokens=100)
    settings = _enabled_settings()
    facade = LLMFacade.from_settings(settings, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="schema"):
        await facade.generate_text(call, "content")


async def test_facade_count_tokens_returns_provider_value(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    stub = _StubClient(create_results=[], count_tokens_input_tokens=77)
    facade = _facade(session_maker, stub)
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=100)

    result = await facade.count_tokens(call, "hello")

    assert result == 77


async def test_facade_count_tokens_raises_not_configured_when_disabled() -> None:
    settings = get_settings().model_copy(update={"llm_enabled": False})
    facade = LLMFacade.from_settings(settings, None)  # type: ignore[arg-type]
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=100)

    with pytest.raises(LLMNotConfigured):
        await facade.count_tokens(call, "hello")


async def test_generate_text_propagates_refusal_and_writes_row(
    session_maker: async_sessionmaker[AsyncSession], db_session: AsyncSession
) -> None:
    """Exercises _dispatch's `except LLMError` branch — a raw LLMError from
    client.request() (not a schema-validation failure) still gets its usage
    row written before propagating."""
    stub = _StubClient(create_results=[_refusal_response("cyber")])
    facade = _facade(session_maker, stub)
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=100)

    with pytest.raises(LLMRefused) as exc_info:
        await facade.generate_text(call, "content", user_id=None)

    assert exc_info.value.category == "cyber"
    rows = await _call_rows(db_session, "learning.chat")
    assert len(rows) == 1
    assert rows[0].outcome == "refused"


async def test_dispatch_with_repair_rejects_schema_none(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Internal guard: _dispatch_with_repair is only ever called by
    generate() after it has already checked call.schema is not None, but
    the guard itself is tested directly here."""
    stub = _StubClient(create_results=[])
    facade = _facade(session_maker, stub)
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=100)

    with pytest.raises(ValueError, match="schema"):
        await facade._dispatch_with_repair(call, "content", model=None, user_id=None)  # type: ignore[attr-defined]


def test_facade_chunk_text_delegates_to_budget_module() -> None:
    settings = get_settings()
    facade = LLMFacade.from_settings(settings, None)  # type: ignore[arg-type]

    chunks = facade.chunk_text(
        "one paragraph, well under budget.", max_tokens=1000, overlap_tokens=0
    )

    assert chunks == ["one paragraph, well under budget."]
