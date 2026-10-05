"""Log hygiene — L2, §8: no prompt, no completion, no API key at any level,
including DEBUG."""

from types import SimpleNamespace

import structlog.testing
from pydantic import BaseModel, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import Settings, get_settings
from disp.core.llm import LLMCall, LLMFacade

SENTINEL_PROMPT = "SENTINEL-PROMPT-do-not-leak-93f7a2"
SENTINEL_COMPLETION = "SENTINEL-COMPLETION-do-not-leak-4b1c9e"
SENTINEL_KEY = "sk-SENTINEL-KEY-do-not-leak-77213d"


class _Schema(BaseModel):
    value: str


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _StubMessages:
    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    async def create(self, **kwargs: object) -> object:
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[_TextBlock(self._response_text)],
            stop_details=None,
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0),
        )

    async def count_tokens(self, **kwargs: object) -> object:
        return SimpleNamespace(input_tokens=10)


class _StubClient:
    def __init__(self, response_text: str) -> None:
        self.messages = _StubMessages(response_text)


async def test_no_prompt_completion_or_key_leaks_at_any_log_level(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = get_settings()
    data = base.model_dump()
    data.update(llm_enabled=True, llm_api_key=SecretStr(SENTINEL_KEY))
    settings = Settings(**data)
    facade = LLMFacade.from_settings(settings, session_maker)
    facade._client = _StubClient(f'{{"value": "{SENTINEL_COMPLETION}"}}')  # type: ignore[attr-defined]
    call = LLMCall(name="learning.chat", schema=_Schema, system="s", max_output_tokens=100)

    with structlog.testing.capture_logs() as captured:
        await facade.generate(call, SENTINEL_PROMPT, user_id=None)

    rendered = repr(captured)
    assert SENTINEL_PROMPT not in rendered
    assert SENTINEL_COMPLETION not in rendered
    assert SENTINEL_KEY not in rendered
    # And the log line the facade IS supposed to write is actually there.
    assert any(event.get("event") == "llm_call_completed" for event in captured)
