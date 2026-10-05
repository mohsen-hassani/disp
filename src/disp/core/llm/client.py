"""The ONLY file in this codebase that imports `anthropic` (L4, M19-llm.md
§10). No module may import this file directly — enforced by
tests/core/test_boundaries.py — because doing so would import the vendor
SDK transitively, defeating the point of hiding the provider behind
LLMFacade.

stop_reason is checked BEFORE response.content is ever read (§4.4): a
refusal returns HTTP 200 with an empty or partial content array, and blind
`content[0]` indexing on that raises an IndexError that looks like a bug in
the caller rather than the policy outcome it actually is.
"""

from dataclasses import dataclass
from typing import cast

import anthropic
from anthropic.types import MessageParam, OutputConfigParam, TextBlockParam
from pydantic import BaseModel

from disp.core.config import Settings
from disp.core.llm.errors import LLMRefused, LLMTruncated, LLMUnavailable

# The public functions below deliberately take plain `dict`s, not
# anthropic's own TypedDicts — those types stay internal to this file (cast
# just before the SDK call), so a caller never has to import them.
Message = dict[str, object]


def build_client(settings: Settings) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(
        api_key=settings.llm_api_key.get_secret_value(),
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


@dataclass(frozen=True)
class RawResponse:
    text: str
    input_tokens: int
    cached_read_tokens: int
    output_tokens: int


def _system_block(system: str) -> list[TextBlockParam]:
    # The system prompt MUST be a module-level constant, never an f-string
    # built per request (§4.3) — a timestamp or user id interpolated into it
    # changes the prefix bytes on every call and the cache read rate goes to
    # zero. Enforcing that is the caller's job (LLMCall.system); this
    # function only attaches the cache breakpoint to whatever it's given.
    return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]


async def request(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    system: str,
    max_output_tokens: int,
    effort: str,
    messages: list[Message],
    schema: type[BaseModel] | None,
) -> RawResponse:
    output_config = cast("OutputConfigParam", {"effort": effort})
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema.model_json_schema()}

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_output_tokens,
            system=_system_block(system),
            messages=cast("list[MessageParam]", messages),
            output_config=output_config,
        )
    except (
        anthropic.APIStatusError,
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
    ) as exc:
        raise LLMUnavailable(f"LLM request failed: {exc}") from exc

    if response.stop_reason == "refusal":
        stop_details = getattr(response, "stop_details", None)
        category = getattr(stop_details, "category", None) if stop_details else None
        raise LLMRefused(category=category)
    if response.stop_reason == "max_tokens":
        raise LLMTruncated()

    text_block = next(
        (block for block in response.content if getattr(block, "type", None) == "text"), None
    )
    text = getattr(text_block, "text", None) if text_block is not None else None
    if not isinstance(text, str):
        raise LLMTruncated()

    usage = response.usage
    return RawResponse(
        text=text,
        input_tokens=usage.input_tokens,
        cached_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        output_tokens=usage.output_tokens,
    )


async def count_tokens(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    system: str,
    messages: list[Message],
) -> int:
    try:
        result = await client.messages.count_tokens(
            model=model,
            system=system,
            messages=cast("list[MessageParam]", messages),
        )
    except (
        anthropic.APIStatusError,
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
    ) as exc:
        raise LLMUnavailable(f"token count request failed: {exc}") from exc
    return result.input_tokens
