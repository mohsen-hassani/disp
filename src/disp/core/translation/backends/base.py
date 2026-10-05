"""TranslationBackend — the provider interface, and the dual-transport base
class every HTTP backend builds on (M22-translation.md §4).

The Protocol is structural: implementations do not subclass it. There is no
registry dict, no entry points and no plugin discovery — the set of backends
is a closed Literal in Settings, because a translation provider is a
deployment choice, not a third-party extension point.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from disp.core.translation.errors import (
    TranslationInvalidResponse,
    TranslationNotSupported,
    TranslationQuotaExceeded,
    TranslationRejected,
    TranslationUnavailable,
)
from disp.core.translation.schema import (
    Detected,
    DetectRequest,
    Feature,
    Translated,
    TranslateRequest,
)

# Provider error bodies are echoed into exception messages so a caller can see
# *why* a request was rejected, but bounded: an unbounded upstream body in an
# exception string is how a 500-page HTML error document ends up in a log.
_MAX_PROVIDER_DETAIL = 200


class TranslationBackend(Protocol):
    name: str
    """Persisted into translation_call.backend, the way StorageBackend.name is
    persisted into core.assets."""

    supports: frozenset[Feature]

    async def translate(self, req: TranslateRequest) -> list[Translated]: ...  # pragma: no cover
    async def detect(self, req: DetectRequest) -> list[Detected]: ...  # pragma: no cover

    def translate_sync(self, req: TranslateRequest) -> list[Translated]: ...  # pragma: no cover
    def detect_sync(self, req: DetectRequest) -> list[Detected]: ...  # pragma: no cover

    async def aclose(self) -> None: ...  # pragma: no cover
    def close(self) -> None: ...  # pragma: no cover


@dataclass(frozen=True)
class HTTPCall:
    """A fully-built request, transport-agnostic. Produced by a subclass's
    pure `_build_*` method and handed to whichever httpx client the caller
    asked for — which is what makes T2 (sync/async parity) structural rather
    than a matter of discipline."""

    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    json: Any = None


class HTTPTranslationBackend:
    """Owns both httpx clients and the status-to-exception mapping, so a
    concrete backend supplies only pure functions: `_build_translate` /
    `_read_translate` and `_build_detect` / `_read_detect`.

    Both clients get an explicit timeout and a retrying transport, and both
    are closed — a deliberate correction of llm/embeddings.py, whose
    httpx.AsyncClient is constructed inline with neither and never closed.

    Note the transport's `retries=` retries connection failures, not HTTP
    status codes: a 429 or 503 arrives as a response, not an exception, and is
    mapped to TranslationUnavailable without a retry (§4).
    """

    name: str = ""
    supports: frozenset[Feature] = frozenset()

    def __init__(
        self,
        *,
        timeout_seconds: int,
        max_retries: int,
        async_transport: httpx.AsyncBaseTransport | None = None,
        sync_transport: httpx.BaseTransport | None = None,
    ) -> None:
        timeout = httpx.Timeout(float(timeout_seconds))
        self._async_client = httpx.AsyncClient(
            timeout=timeout,
            transport=async_transport or httpx.AsyncHTTPTransport(retries=max_retries),
        )
        self._sync_client = httpx.Client(
            timeout=timeout,
            transport=sync_transport or httpx.HTTPTransport(retries=max_retries),
        )

    # ---- the four public methods, identical modulo transport (T2) ----

    async def translate(self, req: TranslateRequest) -> list[Translated]:
        self._check_translate(req)
        payload = await self._send_async(self._build_translate(req))
        return self._parse_translate(payload, req)

    def translate_sync(self, req: TranslateRequest) -> list[Translated]:
        self._check_translate(req)
        payload = self._send_sync(self._build_translate(req))
        return self._parse_translate(payload, req)

    async def detect(self, req: DetectRequest) -> list[Detected]:
        self._check_detect()
        payload = await self._send_async(self._build_detect(req))
        return self._parse_detect(payload, req)

    def detect_sync(self, req: DetectRequest) -> list[Detected]:
        self._check_detect()
        payload = self._send_sync(self._build_detect(req))
        return self._parse_detect(payload, req)

    async def aclose(self) -> None:
        await self._async_client.aclose()

    def close(self) -> None:
        self._sync_client.close()

    # ---- feature gate (T4) ----

    def require(self, feature: Feature) -> None:
        if feature not in self.supports:
            raise TranslationNotSupported(backend=self.name, feature=feature)

    def _check_translate(self, req: TranslateRequest) -> None:
        self.require(Feature.TRANSLATE)
        if req.formality is not None:
            self.require(Feature.FORMALITY)

    def _check_detect(self) -> None:
        self.require(Feature.DETECT)

    # ---- transport ----

    async def _send_async(self, call: HTTPCall) -> Any:
        try:
            response = await self._async_client.request(
                call.method, call.url, headers=dict(call.headers), json=call.json
            )
        except httpx.HTTPError as exc:
            raise TranslationUnavailable(f"translation request failed: {exc}") from exc
        return self._decode(response)

    def _send_sync(self, call: HTTPCall) -> Any:
        try:
            response = self._sync_client.request(
                call.method, call.url, headers=dict(call.headers), json=call.json
            )
        except httpx.HTTPError as exc:
            raise TranslationUnavailable(f"translation request failed: {exc}") from exc
        return self._decode(response)

    def _decode(self, response: httpx.Response) -> Any:
        self._raise_for_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise TranslationInvalidResponse(
                f"{self.name} returned a body that is not JSON (status {response.status_code})"
            ) from exc

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Override to add provider-specific status codes; call super() for
        the general mapping."""
        status = response.status_code
        if status < 400:
            return
        detail = response.text[:_MAX_PROVIDER_DETAIL]
        if status >= 500 or status == 429:
            raise TranslationUnavailable(f"{self.name} returned {status}: {detail}")
        if status == 456:
            raise TranslationQuotaExceeded(f"{self.name} character quota exhausted: {detail}")
        raise TranslationRejected(f"{self.name} rejected the request ({status}): {detail}")

    # ---- parsing: the count invariant (T8) lives here, not in subclasses ----

    def _parse_translate(self, payload: Any, req: TranslateRequest) -> list[Translated]:
        results = self._read_translate(payload)
        self._require_count(len(results), len(req.texts))
        return results

    def _parse_detect(self, payload: Any, req: DetectRequest) -> list[Detected]:
        results = self._read_detect(payload)
        self._require_count(len(results), len(req.texts))
        return results

    def _require_count(self, got: int, expected: int) -> None:
        if got != expected:
            raise TranslationInvalidResponse(
                f"{self.name} returned {got} results for {expected} inputs"
            )

    # ---- subclass hooks: pure functions, no I/O ----

    def _build_translate(self, req: TranslateRequest) -> HTTPCall:
        raise NotImplementedError  # pragma: no cover

    def _read_translate(self, payload: Any) -> list[Translated]:
        raise NotImplementedError  # pragma: no cover

    def _build_detect(self, req: DetectRequest) -> HTTPCall:
        raise NotImplementedError  # pragma: no cover

    def _read_detect(self, payload: Any) -> list[Detected]:
        raise NotImplementedError  # pragma: no cover
