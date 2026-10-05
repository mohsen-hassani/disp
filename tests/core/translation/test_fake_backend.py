"""FakeTranslationBackend itself (M22-translation.md §4.2)."""

import pytest

from disp.core.translation.backends.fake import (
    FakeTranslationBackend,
    deterministic_lang,
)
from disp.core.translation.errors import TranslationNotSupported, TranslationUnavailable
from disp.core.translation.schema import DetectRequest, Feature, TranslateRequest


async def test_unregistered_text_gets_the_marker_transform() -> None:
    """Unlike FakeLLM, an unregistered input does not raise: translation has a
    meaningful identity transform, and the marker proves the target language
    propagated — which a raise would not."""
    backend = FakeTranslationBackend()
    results = await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))
    assert results[0].text == "[DE] Hello"


async def test_registered_text_wins() -> None:
    backend = FakeTranslationBackend()
    backend.register("Hello", target_lang="DE", result="Hallo")
    results = await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))
    assert results[0].text == "Hallo"


async def test_registration_is_keyed_on_the_target_language() -> None:
    backend = FakeTranslationBackend()
    backend.register("Hello", target_lang="DE", result="Hallo")
    results = await backend.translate(TranslateRequest(texts=("Hello",), target_lang="FR"))
    assert results[0].text == "[FR] Hello"


async def test_a_batch_can_mix_registered_results_and_a_failure() -> None:
    backend = FakeTranslationBackend()
    backend.register_error("Boom", error=TranslationUnavailable("upstream down"))
    with pytest.raises(TranslationUnavailable):
        await backend.translate(TranslateRequest(texts=("Hello", "Boom"), target_lang="DE"))


async def test_calls_are_recorded_with_what_was_asked() -> None:
    backend = FakeTranslationBackend()
    await backend.translate(
        TranslateRequest(texts=("Hello",), target_lang="DE", source_lang="EN", formality="more")
    )
    (call,) = backend.calls
    assert call.operation == "translate"
    assert call.texts == ("Hello",)
    assert call.target_lang == "DE"
    assert call.source_lang == "EN"
    assert call.formality == "more"


async def test_sync_and_async_agree() -> None:
    backend = FakeTranslationBackend()
    req = TranslateRequest(texts=("Hello",), target_lang="DE")
    assert await backend.translate(req) == backend.translate_sync(req)

    detect_req = DetectRequest(texts=("Hello",))
    assert await backend.detect(detect_req) == backend.detect_sync(detect_req)


async def test_detection_is_deterministic() -> None:
    backend = FakeTranslationBackend()
    first = await backend.detect(DetectRequest(texts=("Bonjour",)))
    second = await backend.detect(DetectRequest(texts=("Bonjour",)))
    assert first == second
    assert first[0].lang == deterministic_lang("Bonjour")


async def test_registered_detection_wins() -> None:
    backend = FakeTranslationBackend()
    backend.register_detection("Bonjour", lang="FR")
    assert (await backend.detect(DetectRequest(texts=("Bonjour",))))[0].lang == "FR"


async def test_detect_propagates_a_registered_error() -> None:
    backend = FakeTranslationBackend()
    backend.register_error("Boom", error=TranslationUnavailable("down"))
    with pytest.raises(TranslationUnavailable):
        await backend.detect(DetectRequest(texts=("Boom",)))


# ---- T4: the configurable `supports` set is why this is testable at all ----


async def test_missing_translate_support_raises_and_records_nothing() -> None:
    backend = FakeTranslationBackend(supports=frozenset({Feature.DETECT}))
    with pytest.raises(TranslationNotSupported):
        await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))
    assert backend.calls == []


async def test_missing_formality_support_raises_only_when_formality_is_asked_for() -> None:
    backend = FakeTranslationBackend(supports=frozenset({Feature.TRANSLATE, Feature.DETECT}))
    await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))

    with pytest.raises(TranslationNotSupported) as exc:
        await backend.translate(
            TranslateRequest(texts=("Hello",), target_lang="DE", formality="more")
        )
    assert exc.value.feature is Feature.FORMALITY
    assert exc.value.backend == "fake"
    assert len(backend.calls) == 1


async def test_missing_detect_support_raises() -> None:
    backend = FakeTranslationBackend(supports=frozenset({Feature.TRANSLATE}))
    with pytest.raises(TranslationNotSupported):
        await backend.detect(DetectRequest(texts=("Hello",)))
    assert backend.calls == []


async def test_close_is_a_no_op() -> None:
    backend = FakeTranslationBackend()
    await backend.aclose()
    backend.close()
