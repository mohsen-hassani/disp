"""TranslationFacade — the only surface a module may touch
(M22-translation.md §5).

Held on `Platform` as `.translation`. Ties together the backend protocol
(backends/), the core.translation_call accounting table (usage.py), and the
character budget, without itself naming a vendor — the provider's host name
appears in its own backend module only, and a test asserts it (T1).

The sync and async halves are deliberately symmetric rather than one wrapping
the other: spinning up a nested event loop inside a library method raises
inside a running loop and rebuilds a connection pool per call, which would
make the sync surface useless from exactly the place it is most wanted
(§5.1). No such call appears anywhere in this package, and a test greps for
it (T3) — including in comments, so do not name it here either.
"""

import time
import uuid
from collections.abc import Sequence
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from disp.core.config import Settings
from disp.core.translation.backends.base import TranslationBackend
from disp.core.translation.backends.deepl import DeepLBackend
from disp.core.translation.backends.fake import FakeTranslationBackend
from disp.core.translation.errors import (
    TranslationError,
    TranslationInputTooLarge,
    TranslationNotConfigured,
)
from disp.core.translation.schema import (
    Detected,
    DetectRequest,
    Formality,
    Translated,
    TranslateRequest,
    normalize_lang,
)
from disp.core.translation.usage import (
    CallRecord,
    UsageSummary,
    summarize,
    write_call,
    write_call_sync,
)

logger = structlog.get_logger(__name__)


def _build_backend(settings: Settings) -> TranslationBackend:
    """`translation_backend` is a Literal in Settings, so an unknown value
    fails at settings validation — which is why this can end in an unguarded
    return rather than raising on an unrecognised name."""
    if settings.translation_backend == "fake":
        return FakeTranslationBackend()
    return DeepLBackend(
        api_key=settings.translation_api_key.get_secret_value(),
        base_url=settings.translation_base_url,
        timeout_seconds=settings.translation_timeout_seconds,
        max_retries=settings.translation_max_retries,
    )


class TranslationFacade:
    def __init__(
        self,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        sync_session_maker: sessionmaker[Session] | None = None,
        *,
        backend: TranslationBackend | None = None,
    ) -> None:
        self._settings = settings
        self._session_maker = session_maker
        self._sync_session_maker = sync_session_maker
        if backend is not None:
            self._backend: TranslationBackend | None = backend
        else:
            self._backend = _build_backend(settings) if settings.translation_enabled else None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> "TranslationFacade":
        return cls(settings, session_maker)

    # ---- translate ----

    async def translate(
        self,
        texts: Sequence[str],
        *,
        target_lang: str | None = None,
        source_lang: str | None = None,
        formality: Formality | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[Translated]:
        if not texts:
            return []
        backend, req = self._prepare_translate(texts, target_lang, source_lang, formality)
        started = time.monotonic()
        try:
            self._check_budget(req.char_count)
            results = await backend.translate(req)
        except TranslationError as error:
            await self._record_async(
                self._failed(error, "translate", req, user_id, backend, started)
            )
            raise
        await self._record_async(self._ok("translate", req, user_id, backend, started))
        return results

    def translate_sync(
        self,
        texts: Sequence[str],
        *,
        target_lang: str | None = None,
        source_lang: str | None = None,
        formality: Formality | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[Translated]:
        if not texts:
            return []
        backend, req = self._prepare_translate(texts, target_lang, source_lang, formality)
        started = time.monotonic()
        try:
            self._check_budget(req.char_count)
            results = backend.translate_sync(req)
        except TranslationError as error:
            self._record_sync(self._failed(error, "translate", req, user_id, backend, started))
            raise
        self._record_sync(self._ok("translate", req, user_id, backend, started))
        return results

    # ---- detect ----

    async def detect(
        self,
        texts: Sequence[str],
        *,
        user_id: uuid.UUID | None = None,
    ) -> list[Detected]:
        if not texts:
            return []
        backend = self._require_backend()
        req = DetectRequest(texts=tuple(texts))
        started = time.monotonic()
        try:
            self._check_budget(req.char_count)
            results = await backend.detect(req)
        except TranslationError as error:
            await self._record_async(self._failed(error, "detect", req, user_id, backend, started))
            raise
        await self._record_async(self._ok("detect", req, user_id, backend, started))
        return results

    def detect_sync(
        self,
        texts: Sequence[str],
        *,
        user_id: uuid.UUID | None = None,
    ) -> list[Detected]:
        if not texts:
            return []
        backend = self._require_backend()
        req = DetectRequest(texts=tuple(texts))
        started = time.monotonic()
        try:
            self._check_budget(req.char_count)
            results = backend.detect_sync(req)
        except TranslationError as error:
            self._record_sync(self._failed(error, "detect", req, user_id, backend, started))
            raise
        self._record_sync(self._ok("detect", req, user_id, backend, started))
        return results

    # ---- reporting and lifecycle ----

    async def usage(
        self,
        session: AsyncSession,
        *,
        since: datetime | None = None,
        backend: str | None = None,
    ) -> UsageSummary:
        return await summarize(session, since=since, backend=backend)

    async def aclose(self) -> None:
        if self._backend is not None:
            await self._backend.aclose()

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()

    # ---- shared preparation ----

    def _require_backend(self) -> TranslationBackend:
        if not self._settings.translation_enabled or self._backend is None:
            raise TranslationNotConfigured("DISP_TRANSLATION_ENABLED is false")
        return self._backend

    def _prepare_translate(
        self,
        texts: Sequence[str],
        target_lang: str | None,
        source_lang: str | None,
        formality: Formality | None,
    ) -> tuple[TranslationBackend, TranslateRequest]:
        backend = self._require_backend()
        resolved = normalize_lang(target_lang or self._settings.translation_default_target_lang)
        if not resolved:
            # A call-site bug, not a translation outcome — so a plain
            # ValueError, and no usage row. The same distinction
            # LLMFacade.generate() draws when call.schema is None.
            raise ValueError(
                "translate() needs a target_lang, or a DISP_TRANSLATION_DEFAULT_TARGET_LANG default"
            )
        req = TranslateRequest(
            texts=tuple(texts),
            target_lang=resolved,
            source_lang=normalize_lang(source_lang) if source_lang else None,
            formality=formality,
        )
        return backend, req

    def _check_budget(self, char_count: int) -> None:
        """T7 — raised before any network request. The facade never silently
        truncates or splits a caller's input."""
        if char_count > self._settings.translation_max_chars:
            raise TranslationInputTooLarge(
                char_count=char_count, max_chars=self._settings.translation_max_chars
            )

    # ---- accounting ----

    def _ok(
        self,
        operation: str,
        req: TranslateRequest | DetectRequest,
        user_id: uuid.UUID | None,
        backend: TranslationBackend,
        started: float,
    ) -> CallRecord:
        return self._record_data(operation, req, user_id, backend, started, "ok", None)

    def _failed(
        self,
        error: TranslationError,
        operation: str,
        req: TranslateRequest | DetectRequest,
        user_id: uuid.UUID | None,
        backend: TranslationBackend,
        started: float,
    ) -> CallRecord:
        outcome = getattr(error, "outcome", "unavailable")
        return self._record_data(
            operation, req, user_id, backend, started, outcome, f"core.translation.{outcome}"
        )

    def _record_data(
        self,
        operation: str,
        req: TranslateRequest | DetectRequest,
        user_id: uuid.UUID | None,
        backend: TranslationBackend,
        started: float,
        outcome: str,
        error_code: str | None,
    ) -> CallRecord:
        return CallRecord(
            user_id=user_id,
            backend=backend.name,
            operation=operation,
            source_lang=getattr(req, "source_lang", None),
            target_lang=getattr(req, "target_lang", None),
            text_count=len(req.texts),
            char_count=req.char_count,
            latency_ms=int((time.monotonic() - started) * 1000),
            outcome=outcome,
            error_code=error_code,
        )

    async def _record_async(self, record: CallRecord) -> None:
        await write_call(self._session_maker, record)
        self._log(record)

    def _record_sync(self, record: CallRecord) -> None:
        write_call_sync(self._sync_session_maker, record)
        self._log(record)

    def _log(self, record: CallRecord) -> None:
        """The row write and the log line share one call site so the two can
        never drift apart — the shape LLMFacade._record already uses.

        No source text, no translated text and no API key, at any level
        including DEBUG (T6): only backend, operation, the language pair,
        counts, latency and outcome.
        """
        log = logger.info if record.outcome == "ok" else logger.warning
        log(
            "translation_call_completed",
            backend=record.backend,
            operation=record.operation,
            source_lang=record.source_lang,
            target_lang=record.target_lang,
            text_count=record.text_count,
            char_count=record.char_count,
            latency_ms=record.latency_ms,
            outcome=record.outcome,
        )
