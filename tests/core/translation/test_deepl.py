"""DeepL backend — request shape, base-URL derivation, status mapping and the
item-count invariant (M22-translation.md §4.1, §11).

No network, ever: both transports are httpx.MockTransport, which serves the
sync and async client alike.
"""

import httpx
import pytest

from disp.core.translation.backends.deepl import (
    FREE_BASE_URL,
    PRO_BASE_URL,
    DeepLBackend,
    base_url_for,
)
from disp.core.translation.errors import (
    TranslationInvalidResponse,
    TranslationNotSupported,
    TranslationQuotaExceeded,
    TranslationRejected,
    TranslationUnavailable,
)
from disp.core.translation.schema import DetectRequest, Feature, TranslateRequest

FREE_KEY = "0123-4567:fx"
PRO_KEY = "0123-4567"


def _backend(handler: object, *, api_key: str = PRO_KEY, base_url: str = "") -> DeepLBackend:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return DeepLBackend(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=5,
        max_retries=0,
        async_transport=transport,
        sync_transport=transport,
    )


def _ok(*texts: str, source: str = "EN") -> object:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "translations": [
                    {"detected_source_language": source, "text": text} for text in texts
                ]
            },
        )

    return handler


def _status(code: int, body: str = "nope") -> object:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text=body)

    return handler


# ---- base URL derivation (§4.1) ----


def test_free_key_derives_the_free_host() -> None:
    assert base_url_for(FREE_KEY, "") == FREE_BASE_URL


def test_pro_key_derives_the_paid_host() -> None:
    assert base_url_for(PRO_KEY, "") == PRO_BASE_URL


def test_explicit_base_url_wins_over_the_key_suffix() -> None:
    """A self-hosted proxy is a legitimate reason to override — which is also
    the operational trap: swapping a free key for a pro one while this is
    still set 403s every call (§12)."""
    assert base_url_for(FREE_KEY, "https://proxy.internal/") == "https://proxy.internal"


def test_backend_exposes_the_derived_base_url() -> None:
    assert _backend(_ok("x"), api_key=FREE_KEY).base_url == FREE_BASE_URL


# ---- request shape ----


async def test_translate_sends_the_documented_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"translations": [{"detected_source_language": "EN", "text": "Hallo"}]}
        )

    backend = _backend(handler)
    results = await backend.translate(
        TranslateRequest(texts=("Hello",), target_lang="DE", source_lang="EN", formality="more")
    )

    assert results[0].text == "Hallo"
    assert results[0].detected_source_lang == "EN"

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{PRO_BASE_URL}/v2/translate"
    # DeepL-Auth-Key, not Bearer.
    assert request.headers["authorization"] == f"DeepL-Auth-Key {PRO_KEY}"
    import json

    assert json.loads(request.content) == {
        "text": ["Hello"],
        "target_lang": "DE",
        "source_lang": "EN",
        "formality": "more",
    }


async def test_detect_omits_source_lang() -> None:
    """DeepL has no standalone detect endpoint: detection *is* a translate
    call with the source omitted (§4.1)."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"translations": [{"detected_source_language": "FR", "text": "Hello"}]}
        )

    backend = _backend(handler)
    results = await backend.detect(DetectRequest(texts=("Bonjour",)))

    assert results[0].lang == "FR"
    import json

    body = json.loads(seen[0].content)
    assert "source_lang" not in body


# ---- status mapping (§5.2) ----


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (456, TranslationQuotaExceeded),
        (403, TranslationRejected),
        (400, TranslationRejected),
        (429, TranslationUnavailable),
        (503, TranslationUnavailable),
    ],
)
async def test_status_codes_map_to_typed_errors(status: int, expected: type[Exception]) -> None:
    backend = _backend(_status(status))
    with pytest.raises(expected):
        await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))


def test_status_codes_map_the_same_way_on_the_sync_path() -> None:
    backend = _backend(_status(456))
    with pytest.raises(TranslationQuotaExceeded):
        backend.translate_sync(TranslateRequest(texts=("Hello",), target_lang="DE"))


async def test_transport_failure_becomes_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    backend = _backend(handler)
    with pytest.raises(TranslationUnavailable):
        await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))


def test_transport_failure_becomes_unavailable_on_the_sync_path() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    backend = _backend(handler)
    with pytest.raises(TranslationUnavailable):
        backend.translate_sync(TranslateRequest(texts=("Hello",), target_lang="DE"))


# ---- payload validation (T8) ----


async def test_item_count_mismatch_raises_rather_than_misaligning() -> None:
    """T8. A batch whose results come back short produces fluent output
    attached to the wrong record; asserting only "no crash" would pass against
    exactly that."""
    backend = _backend(_ok("Hallo"))
    with pytest.raises(TranslationInvalidResponse, match="1 results for 2 inputs"):
        await backend.translate(TranslateRequest(texts=("Hello", "Bye"), target_lang="DE"))


def test_item_count_is_enforced_on_the_sync_path_too() -> None:
    backend = _backend(_ok("Hallo"))
    with pytest.raises(TranslationInvalidResponse):
        backend.translate_sync(TranslateRequest(texts=("Hello", "Bye"), target_lang="DE"))


async def test_detect_item_count_is_enforced() -> None:
    backend = _backend(_ok("Hallo"))
    with pytest.raises(TranslationInvalidResponse):
        await backend.detect(DetectRequest(texts=("a", "b")))


async def test_non_json_body_raises_invalid_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    backend = _backend(handler)
    with pytest.raises(TranslationInvalidResponse, match="not JSON"):
        await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))


@pytest.mark.parametrize("payload", [{"nope": []}, [], {"translations": "not-a-list"}])
async def test_malformed_translations_array_raises(payload: object) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    backend = _backend(handler)
    with pytest.raises(TranslationInvalidResponse):
        await backend.translate(TranslateRequest(texts=("Hello",), target_lang="DE"))


async def test_missing_detected_source_language_detects_as_empty() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"translations": [{"text": "Hallo"}]})

    backend = _backend(handler)
    assert (await backend.detect(DetectRequest(texts=("Hello",))))[0].lang == ""


# ---- feature gate (T4) ----


async def test_unsupported_feature_raises_before_any_request() -> None:
    """T4. Asserting only the exception type would pass against an
    implementation that calls first and inspects the response."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"translations": []})

    backend = _backend(handler)
    backend.supports = frozenset({Feature.TRANSLATE})  # a provider without formality

    with pytest.raises(TranslationNotSupported) as exc:
        await backend.translate(
            TranslateRequest(texts=("Hello",), target_lang="DE", formality="more")
        )

    assert exc.value.feature is Feature.FORMALITY
    assert exc.value.backend == "deepl"
    assert seen == []


async def test_supports_and_raising_agree_in_both_directions() -> None:
    """§4: `supports` is advisory metadata, never the only gate — so the two
    must not be able to disagree."""
    backend = _backend(_ok("Hallo"))
    for feature in backend.supports:
        backend.require(feature)  # does not raise

    backend.supports = frozenset()
    for feature in Feature:
        with pytest.raises(TranslationNotSupported):
            backend.require(feature)


async def test_clients_close() -> None:
    backend = _backend(_ok("Hallo"))
    await backend.aclose()
    backend.close()
