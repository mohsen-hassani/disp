"""T6 — no source text, no translated text, no API key in any log line, at any
level including DEBUG (M22-translation.md §8).

Asserting only that INFO is clean would pass against an implementation that
logs payloads at DEBUG; asserting only the absence of sentinels would pass
against an implementation that logs nothing at all. So this asserts both.
"""

import httpx
import pytest
import structlog
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import Settings, get_settings
from disp.core.translation import TranslationFacade, TranslationRejected
from disp.core.translation.backends.deepl import DeepLBackend

SENTINEL_SOURCE = "SENTINEL-SOURCE-do-not-leak-93f7a2"
SENTINEL_TRANSLATION = "SENTINEL-TRANSLATION-do-not-leak-4b1c9e"
SENTINEL_KEY = "SENTINEL-KEY-do-not-leak-77213d"


def _facade(session_maker: async_sessionmaker[AsyncSession], handler: object) -> TranslationFacade:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    backend = DeepLBackend(
        api_key=SENTINEL_KEY,
        timeout_seconds=5,
        max_retries=0,
        async_transport=transport,
        sync_transport=transport,
    )
    data = get_settings().model_dump()
    # The key goes into Settings as well as into the backend, so this proves
    # the *configured* credential does not leak either, not just the one the
    # backend happens to hold.
    data.update(
        translation_enabled=True,
        translation_backend="deepl",
        translation_api_key=SecretStr(SENTINEL_KEY),
    )
    return TranslationFacade(Settings(**data), session_maker, backend=backend)


async def test_no_payload_or_key_reaches_the_logs(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "translations": [{"detected_source_language": "EN", "text": SENTINEL_TRANSLATION}]
            },
        )

    facade = _facade(session_maker, handler)

    with structlog.testing.capture_logs() as captured:
        await facade.translate([SENTINEL_SOURCE], target_lang="de")

    rendered = repr(captured)
    assert SENTINEL_SOURCE not in rendered
    assert SENTINEL_TRANSLATION not in rendered
    assert SENTINEL_KEY not in rendered
    # And the line the facade IS supposed to write is actually there.
    completed = [e for e in captured if e.get("event") == "translation_call_completed"]
    assert len(completed) == 1
    assert completed[0]["log_level"] == "info"
    assert completed[0]["outcome"] == "ok"
    assert completed[0]["char_count"] == len(SENTINEL_SOURCE)


async def test_a_failure_logs_at_warning_and_still_leaks_nothing(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad target lang")

    facade = _facade(session_maker, handler)

    with structlog.testing.capture_logs() as captured:
        with pytest.raises(TranslationRejected):
            await facade.translate([SENTINEL_SOURCE], target_lang="de")

    rendered = repr(captured)
    assert SENTINEL_SOURCE not in rendered
    assert SENTINEL_KEY not in rendered
    (completed,) = [e for e in captured if e.get("event") == "translation_call_completed"]
    assert completed["log_level"] == "warning"
    assert completed["outcome"] == "rejected"
