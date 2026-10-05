"""LLMFacade — the only surface a module may touch (M19-llm.md §4).

Held on `Platform` as `.llm`. Ties together client.py (the only
anthropic-importing file), usage.py (the core.llm_call accounting table),
budget.py, and embeddings.py, without itself importing `anthropic` — kept
out of client.py (decision 4 of the M19 implementation plan) so "the only
file that imports anthropic" stays true at a glance.
"""

import time
import uuid
from datetime import datetime

import httpx
import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import Settings
from disp.core.llm import budget as budget_module
from disp.core.llm import client
from disp.core.llm.embeddings import (
    EmbeddingProvider,
    LocalEmbeddingProvider,
    VoyageEmbeddingProvider,
)
from disp.core.llm.errors import (
    LLMError,
    LLMInputTooLarge,
    LLMInvalidOutput,
    LLMNotConfigured,
)
from disp.core.llm.schema import LLMCall
from disp.core.llm.usage import UsageSummary, summarize, write_call

logger = structlog.get_logger(__name__)


def _build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "local":
        return LocalEmbeddingProvider(model=settings.embedding_model)
    return VoyageEmbeddingProvider(
        api_key=settings.embedding_api_key.get_secret_value(),
        model=settings.embedding_model,
        http_client=httpx.AsyncClient(),
    )


class LLMFacade:
    def __init__(self, settings: Settings, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._settings = settings
        self._session_maker = session_maker
        self._client = client.build_client(settings) if settings.llm_enabled else None
        self._embedding_provider = (
            _build_embedding_provider(settings) if settings.embedding_enabled else None
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, session_maker: async_sessionmaker[AsyncSession]
    ) -> "LLMFacade":
        return cls(settings, session_maker)

    async def _record(
        self,
        *,
        user_id: uuid.UUID | None,
        call_name: str,
        model: str,
        input_tokens: int,
        cached_read_tokens: int,
        output_tokens: int,
        latency_ms: int,
        outcome: str,
        error_code: str | None,
    ) -> None:
        """Writes the core.llm_call row AND logs one structlog line — kept as
        one call site so the two can never drift apart. No prompt, no
        completion, no API key is logged at any level (L2, §8): only the
        call name, model, token counts, latency, and outcome."""
        await write_call(
            self._session_maker,
            user_id=user_id,
            call_name=call_name,
            model=model,
            input_tokens=input_tokens,
            cached_read_tokens=cached_read_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            outcome=outcome,
            error_code=error_code,
        )
        log = logger.info if outcome == "ok" else logger.warning
        log(
            "llm_call_completed",
            call_name=call_name,
            model=model,
            outcome=outcome,
            input_tokens=input_tokens,
            cached_read_tokens=cached_read_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

    async def generate(
        self,
        call: LLMCall,
        user_content: str,
        *,
        user_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> BaseModel:
        if call.schema is None:
            raise ValueError(
                "LLMCall.schema must be set for generate() — use generate_text() for free text"
            )
        text, resolved_model, latency_ms, raw = await self._dispatch_with_repair(
            call, user_content, model=model, user_id=user_id
        )
        await self._record(
            user_id=user_id,
            call_name=call.name,
            model=resolved_model,
            input_tokens=raw.input_tokens,
            cached_read_tokens=raw.cached_read_tokens,
            output_tokens=raw.output_tokens,
            latency_ms=latency_ms,
            outcome="ok",
            error_code=None,
        )
        return call.schema.model_validate_json(text)

    async def generate_text(
        self,
        call: LLMCall,
        user_content: str,
        *,
        user_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> str:
        if call.schema is not None:
            raise ValueError("generate_text() requires LLMCall.schema to be None")
        text, resolved_model, latency_ms, raw = await self._dispatch(
            call, user_content, model=model, user_id=user_id
        )
        await self._record(
            user_id=user_id,
            call_name=call.name,
            model=resolved_model,
            input_tokens=raw.input_tokens,
            cached_read_tokens=raw.cached_read_tokens,
            output_tokens=raw.output_tokens,
            latency_ms=latency_ms,
            outcome="ok",
            error_code=None,
        )
        return text

    async def count_tokens(
        self, call: LLMCall, user_content: str, *, model: str | None = None
    ) -> int:
        if not self._settings.llm_enabled or self._client is None:
            raise LLMNotConfigured("DISP_LLM_ENABLED is false")
        resolved_model = model or self._settings.llm_model
        return await client.count_tokens(
            self._client,
            model=resolved_model,
            system=call.system,
            messages=[{"role": "user", "content": user_content}],
        )

    async def embed(
        self, texts: list[str], *, user_id: uuid.UUID | None = None
    ) -> list[list[float]]:
        # Embeddings have no LLMCall (no <domain>.<name>) and are a
        # separately-configured vendor from generation (§7) — they are not
        # part of the core.llm_call accounting table, which is keyed on a
        # call name embed() never has.
        if not self._settings.embedding_enabled or self._embedding_provider is None:
            raise LLMNotConfigured("DISP_EMBEDDING_ENABLED is false")
        vectors = await self._embedding_provider.embed(texts)
        for vector in vectors:
            if len(vector) != self._settings.embedding_dimensions:
                raise LLMInvalidOutput(
                    f"embedding provider returned a {len(vector)}-dimension vector, "
                    f"expected {self._settings.embedding_dimensions} "
                    f"(DISP_EMBEDDING_DIMENSIONS)"
                )
        return vectors

    async def usage(
        self,
        session: AsyncSession,
        *,
        since: datetime | None = None,
        call_name: str | None = None,
    ) -> UsageSummary:
        return await summarize(session, since=since, call_name=call_name)

    def chunk_text(self, text: str, *, max_tokens: int, overlap_tokens: int) -> list[str]:
        return budget_module.chunk_text(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)

    async def _dispatch(
        self,
        call: LLMCall,
        user_content: str,
        *,
        model: str | None,
        user_id: uuid.UUID | None,
    ) -> tuple[str, str, int, client.RawResponse]:
        """Budget check + one generation request. No repair loop — used
        directly by generate_text() (nothing to repair without a schema) and
        as the first attempt inside _dispatch_with_repair()."""
        if not self._settings.llm_enabled or self._client is None:
            raise LLMNotConfigured("DISP_LLM_ENABLED is false")

        resolved_model = model or self._settings.llm_model
        max_output_tokens = min(call.max_output_tokens, self._settings.llm_max_output_tokens)
        messages: list[client.Message] = [{"role": "user", "content": user_content}]

        input_tokens = await client.count_tokens(
            self._client, model=resolved_model, system=call.system, messages=messages
        )
        if input_tokens > call.max_input_tokens:
            error = LLMInputTooLarge(
                input_tokens=input_tokens, max_input_tokens=call.max_input_tokens
            )
            await self._record(
                user_id=user_id,
                call_name=call.name,
                model=resolved_model,
                input_tokens=input_tokens,
                cached_read_tokens=0,
                output_tokens=0,
                latency_ms=0,
                outcome=error.outcome,
                error_code=f"core.llm.{error.outcome}",
            )
            raise error

        started = time.monotonic()
        try:
            raw = await client.request(
                self._client,
                model=resolved_model,
                system=call.system,
                max_output_tokens=max_output_tokens,
                effort=call.effort,
                messages=messages,
                schema=call.schema,
            )
        except LLMError as error:
            latency_ms = int((time.monotonic() - started) * 1000)
            outcome = getattr(error, "outcome", "unavailable")
            await self._record(
                user_id=user_id,
                call_name=call.name,
                model=resolved_model,
                input_tokens=0,
                cached_read_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                outcome=outcome,
                error_code=f"core.llm.{outcome}",
            )
            raise
        latency_ms = int((time.monotonic() - started) * 1000)
        return raw.text, resolved_model, latency_ms, raw

    async def _dispatch_with_repair(
        self,
        call: LLMCall,
        user_content: str,
        *,
        model: str | None,
        user_id: uuid.UUID | None,
    ) -> tuple[str, str, int, client.RawResponse]:
        """One repair attempt on schema-validation failure (§4.4): re-send
        with the validation error appended as a user turn. A second failure
        raises LLMInvalidOutput. Not used by generate_text(), which has no
        schema to validate against."""
        if call.schema is None:
            raise ValueError("_dispatch_with_repair requires LLMCall.schema to be set")
        text, resolved_model, latency_ms, raw = await self._dispatch(
            call, user_content, model=model, user_id=user_id
        )
        try:
            call.schema.model_validate_json(text)
        except ValidationError as first_error:
            repaired_content = (
                f"{user_content}\n\n---\nYour previous response was:\n{text}\n\n"
                f"That response failed schema validation with this error:\n{first_error}\n\n"
                "Respond again with output that matches the schema exactly."
            )
            text, resolved_model, repair_latency_ms, raw = await self._dispatch(
                call, repaired_content, model=model, user_id=user_id
            )
            latency_ms += repair_latency_ms
            try:
                call.schema.model_validate_json(text)
            except ValidationError as second_error:
                error = LLMInvalidOutput(str(second_error))
                await self._record(
                    user_id=user_id,
                    call_name=call.name,
                    model=resolved_model,
                    input_tokens=raw.input_tokens,
                    cached_read_tokens=raw.cached_read_tokens,
                    output_tokens=raw.output_tokens,
                    latency_ms=latency_ms,
                    outcome=error.outcome,
                    error_code=f"core.llm.{error.outcome}",
                )
                raise error from second_error
        return text, resolved_model, latency_ms, raw
