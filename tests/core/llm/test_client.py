"""client.py — the only file importing `anthropic` (M19-llm.md §4.4, §12).

No network, ever: every anthropic.AsyncAnthropic call is replaced with a
hand-rolled stub carrying the same duck-typed shape (`.messages.create()`,
`.messages.count_tokens()`), so these tests exercise client.py's own
translation logic (stop_reason handling, usage extraction, exception
wrapping) without a real transport underneath.
"""

from types import SimpleNamespace

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from disp.core.llm import client
from disp.core.llm.errors import LLMRefused, LLMTruncated, LLMUnavailable


class _OutputSchema(BaseModel):
    value: str


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _StubMessages:
    def __init__(
        self, *, create_result: object = None, count_tokens_input_tokens: int = 42
    ) -> None:
        self._create_result = create_result
        self._count_tokens_input_tokens = count_tokens_input_tokens
        self.create_calls: list[dict[str, object]] = []
        self.count_tokens_calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.create_calls.append(kwargs)
        if isinstance(self._create_result, BaseException):
            raise self._create_result
        return self._create_result

    async def count_tokens(self, **kwargs: object) -> object:
        self.count_tokens_calls.append(kwargs)
        return SimpleNamespace(input_tokens=self._count_tokens_input_tokens)


class _StubClient:
    def __init__(self, **kwargs: object) -> None:
        self.messages = _StubMessages(**kwargs)


def _response(*, stop_reason: str, content: list[object], stop_details: object = None) -> object:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        stop_details=stop_details,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=3),
    )


async def test_request_returns_text_and_usage_on_success() -> None:
    stub = _StubClient(
        create_result=_response(stop_reason="end_turn", content=[_TextBlock('{"value": "ok"}')])
    )
    raw = await client.request(
        stub,
        model="claude-opus-5",
        system="system prompt",
        max_output_tokens=100,
        effort="high",
        messages=[{"role": "user", "content": "hi"}],
        schema=_OutputSchema,
    )
    assert raw.text == '{"value": "ok"}'
    assert raw.input_tokens == 10
    assert raw.output_tokens == 5
    assert raw.cached_read_tokens == 3


async def test_request_attaches_cache_control_to_system_block() -> None:
    stub = _StubClient(create_result=_response(stop_reason="end_turn", content=[_TextBlock("x")]))
    await client.request(
        stub,
        model="claude-opus-5",
        system="stable system prompt",
        max_output_tokens=100,
        effort="high",
        messages=[{"role": "user", "content": "hi"}],
        schema=None,
    )
    sent_system = stub.messages.create_calls[0]["system"]
    assert sent_system == [
        {"type": "text", "text": "stable system prompt", "cache_control": {"type": "ephemeral"}}
    ]


async def test_request_stop_reason_refusal_raises_before_reading_content() -> None:
    # content is empty, like a real refusal response — a naive content[0]
    # would IndexError; this must raise LLMRefused instead (§4.4, L6).
    stub = _StubClient(
        create_result=_response(
            stop_reason="refusal", content=[], stop_details=SimpleNamespace(category="cyber")
        )
    )
    with pytest.raises(LLMRefused) as exc_info:
        await client.request(
            stub,
            model="claude-opus-5",
            system="s",
            max_output_tokens=100,
            effort="high",
            messages=[],
            schema=None,
        )
    assert exc_info.value.category == "cyber"


async def test_request_stop_reason_max_tokens_raises_truncated_not_retried() -> None:
    stub = _StubClient(
        create_result=_response(stop_reason="max_tokens", content=[_TextBlock("partial")])
    )
    with pytest.raises(LLMTruncated):
        await client.request(
            stub,
            model="claude-opus-5",
            system="s",
            max_output_tokens=100,
            effort="high",
            messages=[],
            schema=None,
        )
    assert len(stub.messages.create_calls) == 1


async def test_request_wraps_connection_error_as_unavailable() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    stub = _StubClient(create_result=anthropic.APIConnectionError(request=request))
    with pytest.raises(LLMUnavailable):
        await client.request(
            stub,
            model="claude-opus-5",
            system="s",
            max_output_tokens=100,
            effort="high",
            messages=[],
            schema=None,
        )


async def test_request_wraps_status_error_as_unavailable() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=503, request=request)
    stub = _StubClient(
        create_result=anthropic.APIStatusError("server error", response=response, body=None)
    )
    with pytest.raises(LLMUnavailable):
        await client.request(
            stub,
            model="claude-opus-5",
            system="s",
            max_output_tokens=100,
            effort="high",
            messages=[],
            schema=None,
        )


async def test_request_raises_truncated_when_no_text_block_present() -> None:
    # A response with no text content block at all (e.g. only a thinking
    # block) is not a refusal or a max_tokens stop, but there's still no
    # text to return — treated the same as truncation.
    stub = _StubClient(
        create_result=_response(stop_reason="end_turn", content=[SimpleNamespace(type="thinking")])
    )
    with pytest.raises(LLMTruncated):
        await client.request(
            stub,
            model="claude-opus-5",
            system="s",
            max_output_tokens=100,
            effort="high",
            messages=[],
            schema=None,
        )


async def test_count_tokens_returns_provider_value() -> None:
    stub = _StubClient(count_tokens_input_tokens=1234)
    result = await client.count_tokens(
        stub, model="claude-opus-5", system="s", messages=[{"role": "user", "content": "hi"}]
    )
    assert result == 1234


async def test_count_tokens_wraps_transport_failure() -> None:
    request = httpx.Request("GET", "https://api.anthropic.com/v1/messages/count_tokens")
    stub = _StubClient()

    async def _raise(**kwargs: object) -> object:
        raise anthropic.APIConnectionError(request=request)

    stub.messages.count_tokens = _raise  # type: ignore[method-assign]
    with pytest.raises(LLMUnavailable):
        await client.count_tokens(stub, model="claude-opus-5", system="s", messages=[])
