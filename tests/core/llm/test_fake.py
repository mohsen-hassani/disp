"""FakeLLM — the test double every module test uses instead of a real
LLMFacade (M19-llm.md §9)."""

from uuid import uuid4

import pytest
from pydantic import BaseModel

from disp.core.llm import FakeLLM, LLMCall
from disp.core.llm.errors import LLMInvalidOutput, LLMNotConfigured, LLMRefused


class _TopicAlignment(BaseModel):
    topics: list[str]


async def test_unregistered_call_raises_loudly() -> None:
    fake = FakeLLM()
    call = LLMCall(
        name="learning.align_topics", schema=_TopicAlignment, system="s", max_output_tokens=10
    )
    with pytest.raises(LLMNotConfigured):
        await fake.generate(call, "content")


async def test_registered_response_returned_and_recorded() -> None:
    fake = FakeLLM()
    response = _TopicAlignment(topics=["a", "b"])
    fake.register("learning.align_topics", response)
    call = LLMCall(
        name="learning.align_topics", schema=_TopicAlignment, system="s", max_output_tokens=10
    )
    user_id = uuid4()

    result = await fake.generate(call, "content", user_id=user_id)

    assert result is response
    assert len(fake.calls) == 1
    assert fake.calls[0].name == "learning.align_topics"
    assert fake.calls[0].user_content == "content"
    assert fake.calls[0].user_id == user_id


async def test_registered_error_is_raised() -> None:
    fake = FakeLLM()
    fake.register_error("learning.grade_quiz", LLMRefused(category="cyber"))
    call = LLMCall(
        name="learning.grade_quiz", schema=_TopicAlignment, system="s", max_output_tokens=10
    )

    with pytest.raises(LLMRefused) as exc_info:
        await fake.generate(call, "content")
    assert exc_info.value.category == "cyber"
    # The call is still recorded even though it raised.
    assert len(fake.calls) == 1


async def test_registered_response_type_mismatch_raises_invalid_output() -> None:
    class _Other(BaseModel):
        x: int

    fake = FakeLLM()
    fake.register("learning.align_topics", _Other(x=1))
    call = LLMCall(
        name="learning.align_topics", schema=_TopicAlignment, system="s", max_output_tokens=10
    )

    with pytest.raises(LLMInvalidOutput):
        await fake.generate(call, "content")


async def test_generate_text_returns_registered_string() -> None:
    fake = FakeLLM()
    fake.register("learning.chat", "hello there")
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=10)

    result = await fake.generate_text(call, "hi")

    assert result == "hello there"


async def test_embed_is_deterministic_and_matches_configured_dimensions() -> None:
    fake = FakeLLM(embedding_dimensions=16)
    vectors_first = await fake.embed(["hello", "world"])
    vectors_second = await fake.embed(["hello", "world"])

    assert vectors_first == vectors_second
    assert all(len(v) == 16 for v in vectors_first)
    assert vectors_first[0] != vectors_first[1]


async def test_generate_text_unregistered_call_raises_loudly() -> None:
    fake = FakeLLM()
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=10)
    with pytest.raises(LLMNotConfigured):
        await fake.generate_text(call, "hi")


async def test_generate_text_registered_error_is_raised() -> None:
    fake = FakeLLM()
    fake.register_error("learning.chat", LLMRefused(category="weapons"))
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=10)

    with pytest.raises(LLMRefused) as exc_info:
        await fake.generate_text(call, "hi")
    assert exc_info.value.category == "weapons"


async def test_generate_text_type_mismatch_raises_invalid_output() -> None:
    fake = FakeLLM()
    fake.register("learning.chat", _TopicAlignment(topics=["not-a-string-response"]))
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=10)

    with pytest.raises(LLMInvalidOutput):
        await fake.generate_text(call, "hi")


async def test_count_tokens_returns_a_positive_estimate() -> None:
    fake = FakeLLM()
    call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=10)

    assert await fake.count_tokens(call, "some content here") > 0
    assert await fake.count_tokens(call, "") == 1


async def test_usage_aggregates_recorded_calls_filtered_by_name() -> None:
    fake = FakeLLM()
    fake.register("learning.chat", "hi")
    fake.register("learning.explain", "ok")
    chat_call = LLMCall(name="learning.chat", schema=None, system="s", max_output_tokens=10)
    explain_call = LLMCall(name="learning.explain", schema=None, system="s", max_output_tokens=10)
    await fake.generate_text(chat_call, "a")
    await fake.generate_text(chat_call, "b")
    await fake.generate_text(explain_call, "c")

    all_usage = await fake.usage(None)
    assert all_usage.total_calls == 3

    chat_usage = await fake.usage(None, call_name="learning.chat")
    assert chat_usage.total_calls == 2
    assert all(row.call_name == "learning.chat" for row in chat_usage.rows)
