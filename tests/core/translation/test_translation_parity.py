"""T2 — the sync and async surfaces are one implementation with two
transports (M22-translation.md §4, §11).

The assertion is deliberately on the *captured requests*, not just the
results: two implementations that both return the right answer can still
diverge on everything an assertion does not cover, and that is exactly where
the bug would be.
"""

import httpx

from disp.core.translation.backends.deepl import DeepLBackend
from disp.core.translation.schema import DetectRequest, TranslateRequest


def _capture() -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "translations": [
                    {"detected_source_language": "EN", "text": "Hallo"},
                    {"detected_source_language": "EN", "text": "Tschuss"},
                ]
            },
        )

    return seen, httpx.MockTransport(handler)


def _backend(async_transport: httpx.MockTransport, sync_transport: httpx.MockTransport):  # type: ignore[no-untyped-def]
    return DeepLBackend(
        api_key="key:fx",
        timeout_seconds=5,
        max_retries=0,
        async_transport=async_transport,
        sync_transport=sync_transport,
    )


def _comparable(request: httpx.Request) -> tuple[str, str, dict[str, str], bytes]:
    # host/user-agent/content-length are httpx's own and identical by
    # construction; the interesting headers are the ones the backend sets.
    headers = {k: v for k, v in request.headers.items() if k in {"authorization", "content-type"}}
    return request.method, str(request.url), headers, request.content


async def test_translate_issues_identical_requests_on_both_paths() -> None:
    async_seen, async_transport = _capture()
    sync_seen, sync_transport = _capture()
    backend = _backend(async_transport, sync_transport)

    req = TranslateRequest(
        texts=("Hello", "Bye"), target_lang="DE", source_lang="EN", formality="less"
    )
    async_results = await backend.translate(req)
    sync_results = backend.translate_sync(req)

    assert _comparable(async_seen[0]) == _comparable(sync_seen[0])
    assert async_results == sync_results


async def test_detect_issues_identical_requests_on_both_paths() -> None:
    async_seen, async_transport = _capture()
    sync_seen, sync_transport = _capture()
    backend = _backend(async_transport, sync_transport)

    req = DetectRequest(texts=("Hello", "Bye"))
    async_results = await backend.detect(req)
    sync_results = backend.detect_sync(req)

    assert _comparable(async_seen[0]) == _comparable(sync_seen[0])
    assert async_results == sync_results
