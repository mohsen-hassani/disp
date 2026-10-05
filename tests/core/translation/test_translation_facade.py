"""TranslationFacade's async surface — invariants T5, T7, and the config gate
(M22-translation.md §5, §7, §11).

Uses the fake *backend* (not a fake facade) so the facade under test is the
real one, and a REAL Postgres session via the `session_maker` fixture, so T5's
"the row survives even when the caller's own transaction is about to roll
back" is proven against the database rather than simulated.
"""

import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import Settings, get_settings
from disp.core.models import TranslationCallRow
from disp.core.translation import (
    FakeTranslationBackend,
    TranslationFacade,
    TranslationInputTooLarge,
    TranslationNotConfigured,
    TranslationNotSupported,
    TranslationUnavailable,
)
from disp.core.translation.backends.deepl import FREE_BASE_URL, DeepLBackend
from disp.core.translation.schema import Feature


def _settings(**overrides: object) -> Settings:
    data = get_settings().model_dump()
    data.update(translation_enabled=True, translation_backend="fake")
    data.update(overrides)
    return Settings(**data)


def _facade(
    session_maker: async_sessionmaker[AsyncSession],
    backend: FakeTranslationBackend | None = None,
    **overrides: object,
) -> TranslationFacade:
    return TranslationFacade(
        _settings(**overrides),
        session_maker,
        backend=backend if backend is not None else FakeTranslationBackend(),
    )


async def _rows(session: AsyncSession) -> list[TranslationCallRow]:
    result = await session.execute(select(TranslationCallRow))
    return list(result.scalars())


async def _row_count(session: AsyncSession) -> int:
    return (
        await session.execute(select(func.count()).select_from(TranslationCallRow))
    ).scalar_one()


# ---- happy path ----


async def test_translate_returns_one_result_per_input_in_order(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    backend = FakeTranslationBackend()
    backend.register("Hello", target_lang="DE", result="Hallo")
    facade = _facade(session_maker, backend)

    results = await facade.translate(["Hello", "Bye"], target_lang="de")

    assert [r.text for r in results] == ["Hallo", "[DE] Bye"]


async def test_translate_writes_one_ok_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    facade = _facade(session_maker)
    user_id = uuid.uuid4()

    await facade.translate(["Hello", "Bye"], target_lang="de", source_lang="en", user_id=user_id)

    async with session_maker() as session:
        (row,) = await _rows(session)
    assert row.backend == "fake"
    assert row.operation == "translate"
    assert row.outcome == "ok"
    assert row.error_code is None
    assert row.user_id == user_id
    assert row.text_count == 2
    # "Hello" + "Bye" — source characters, the unit every provider meters.
    assert row.char_count == 8
    assert row.source_lang == "EN"
    assert row.target_lang == "DE"


async def test_detect_writes_a_detect_row_with_no_target_lang(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    facade = _facade(session_maker)

    results = await facade.detect(["Bonjour"])

    assert len(results) == 1
    async with session_maker() as session:
        (row,) = await _rows(session)
    assert row.operation == "detect"
    assert row.target_lang is None
    assert row.char_count == 7


async def test_default_target_lang_is_used_when_the_caller_omits_one(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    facade = _facade(session_maker, translation_default_target_lang="fr")
    results = await facade.translate(["Hello"])
    assert results[0].text == "[FR] Hello"


# ---- T5: durability ----


async def test_a_failing_call_still_commits_its_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """T5. Asserted from a *separate* session — asserting inside the caller's
    own (about-to-roll-back) transaction proves nothing."""
    backend = FakeTranslationBackend()
    backend.register_error("Boom", error=TranslationUnavailable("upstream down"))
    facade = _facade(session_maker, backend)

    with pytest.raises(TranslationUnavailable):
        await facade.translate(["Boom"], target_lang="de")

    async with session_maker() as session:
        (row,) = await _rows(session)
    assert row.outcome == "unavailable"
    assert row.error_code == "core.translation.unavailable"


async def test_unsupported_feature_is_recorded_as_not_supported(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    backend = FakeTranslationBackend(supports=frozenset({Feature.TRANSLATE, Feature.DETECT}))
    facade = _facade(session_maker, backend)

    with pytest.raises(TranslationNotSupported):
        await facade.translate(["Hello"], target_lang="de", formality="more")

    async with session_maker() as session:
        (row,) = await _rows(session)
    assert row.outcome == "not_supported"
    assert row.error_code == "core.translation.not_supported"


# ---- the config gate ----


async def test_disabled_facade_raises_and_writes_no_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A config-gate rejection is not a "call" in the accounting sense — no
    backend was ever constructed. Asserting only the exception would pass
    against an implementation that records one anyway."""
    facade = TranslationFacade(_settings(translation_enabled=False), session_maker)

    with pytest.raises(TranslationNotConfigured):
        await facade.translate(["Hello"], target_lang="de")
    with pytest.raises(TranslationNotConfigured):
        await facade.detect(["Hello"])

    async with session_maker() as session:
        assert await _row_count(session) == 0


async def test_disabled_facade_builds_no_backend() -> None:
    facade = TranslationFacade(_settings(translation_enabled=False))
    # aclose()/close() must stay safe to call on a facade that never built one.
    await facade.aclose()
    facade.close()


async def test_enabled_facade_builds_the_configured_backend(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """§4.3's promise that swapping providers is a settings change: the
    facade, not the caller, resolves DISP_TRANSLATION_BACKEND. No `backend=`
    override here — that is the point."""
    facade = TranslationFacade(_settings(), session_maker)
    assert (await facade.translate(["Hello"], target_lang="de"))[0].text == "[DE] Hello"
    await facade.aclose()
    facade.close()


async def test_deepl_backend_is_built_from_settings_alone() -> None:
    """The other half of the substitutability claim, and the only place the
    real provider is constructed the way production constructs it — from
    settings, with the free-tier host derived from the key's suffix. No
    request is made, so no network and no usage row."""
    facade = TranslationFacade(
        _settings(translation_backend="deepl", translation_api_key=SecretStr("test-key:fx"))
    )
    backend = facade._backend

    assert isinstance(backend, DeepLBackend)
    assert backend.name == "deepl"
    assert backend.base_url == FREE_BASE_URL

    await facade.aclose()
    facade.close()


# ---- T7: budget ----


async def test_oversized_batch_raises_before_the_backend_is_called(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """T7. Asserting only the exception type would pass against an
    implementation that calls first and checks after."""
    backend = FakeTranslationBackend()
    facade = _facade(session_maker, backend, translation_max_chars=5)

    with pytest.raises(TranslationInputTooLarge) as exc:
        await facade.translate(["a" * 10], target_lang="de")

    assert exc.value.char_count == 10
    assert exc.value.max_chars == 5
    assert backend.calls == []

    async with session_maker() as session:
        (row,) = await _rows(session)
    assert row.outcome == "too_large"
    assert row.error_code == "core.translation.too_large"


async def test_detect_is_budgeted_too(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    backend = FakeTranslationBackend()
    facade = _facade(session_maker, backend, translation_max_chars=5)

    with pytest.raises(TranslationInputTooLarge):
        await facade.detect(["a" * 10])
    assert backend.calls == []


# ---- call-site errors ----


async def test_missing_target_lang_is_a_value_error_and_writes_no_row(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A call-site bug, not a translation outcome — so a plain ValueError and
    no usage row, the same distinction LLMFacade.generate() draws."""
    facade = _facade(session_maker)

    with pytest.raises(ValueError, match="target_lang"):
        await facade.translate(["Hello"])

    async with session_maker() as session:
        assert await _row_count(session) == 0


async def test_empty_batch_short_circuits(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Zero inputs, zero outputs, zero characters, no provider call — and no
    row, because nothing was dispatched."""
    backend = FakeTranslationBackend()
    facade = _facade(session_maker, backend)

    assert await facade.translate([], target_lang="de") == []
    assert await facade.detect([]) == []
    assert backend.calls == []

    async with session_maker() as session:
        assert await _row_count(session) == 0


# ---- usage ----


async def test_usage_summarizes_what_was_recorded(
    session_maker: async_sessionmaker[AsyncSession],
    db_session: AsyncSession,
) -> None:
    facade = _facade(session_maker)
    await facade.translate(["Hello"], target_lang="de")
    await facade.detect(["Bonjour"])

    summary = await facade.usage(db_session)

    assert summary.total_calls == 2
    assert summary.total_texts == 2
    assert summary.total_chars == 12
    assert {row.operation for row in summary.rows} == {"translate", "detect"}
