"""FakeLLM — the test double every module test uses instead of a real
LLMFacade (M19-llm.md §9). Part of disp.core.llm's public surface.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel

from disp.core.llm.embeddings import deterministic_vector
from disp.core.llm.errors import LLMError, LLMInvalidOutput, LLMNotConfigured
from disp.core.llm.schema import LLMCall
from disp.core.llm.usage import UsageRow, UsageSummary


@dataclass(frozen=True)
class RecordedCall:
    name: str
    user_content: str
    user_id: uuid.UUID | None


class FakeLLM:
    def __init__(self, *, embedding_dimensions: int = 1024) -> None:
        self._responses: dict[str, BaseModel | str] = {}
        self._errors: dict[str, LLMError] = {}
        self._embed_error: LLMError | None = None
        self._embedding_dimensions = embedding_dimensions
        self.calls: list[RecordedCall] = []

    def register(self, name: str, response: BaseModel | str) -> None:
        """`response` is already a constructed (and therefore validated)
        BaseModel instance, or a plain str for generate_text() call sites —
        the "validate on registration" requirement (§9) is satisfied by
        construction, since an invalid BaseModel could never have been
        built in the first place."""
        self._responses[name] = response

    def register_error(self, name: str, error: LLMError) -> None:
        self._errors[name] = error

    def register_embed_error(self, error: LLMError) -> None:
        """`embed()` has no `call.name` to key by (§7's callers pass a bare
        text list) — one error applies to every `embed()` call on this
        instance, same as the real `LLMFacade.embed()` failing uniformly
        when `DISP_EMBEDDING_ENABLED=false`."""
        self._embed_error = error

    async def generate(
        self,
        call: LLMCall,
        user_content: str,
        *,
        user_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> BaseModel:
        self.calls.append(RecordedCall(call.name, user_content, user_id))
        if call.name in self._errors:
            raise self._errors[call.name]
        if call.name not in self._responses:
            raise LLMNotConfigured(f"FakeLLM: no response registered for {call.name!r}")
        response = self._responses[call.name]
        if call.schema is None or not isinstance(response, call.schema):
            raise LLMInvalidOutput(
                f"FakeLLM: registered response for {call.name!r} is not a {call.schema}"
            )
        return response

    async def generate_text(
        self,
        call: LLMCall,
        user_content: str,
        *,
        user_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> str:
        self.calls.append(RecordedCall(call.name, user_content, user_id))
        if call.name in self._errors:
            raise self._errors[call.name]
        if call.name not in self._responses:
            raise LLMNotConfigured(f"FakeLLM: no response registered for {call.name!r}")
        response = self._responses[call.name]
        if not isinstance(response, str):
            raise LLMInvalidOutput(f"FakeLLM: registered response for {call.name!r} is not a str")
        return response

    async def count_tokens(
        self, call: LLMCall, user_content: str, *, model: str | None = None
    ) -> int:
        return max(1, len(user_content) // 4)

    async def embed(
        self, texts: list[str], *, user_id: uuid.UUID | None = None
    ) -> list[list[float]]:
        if self._embed_error is not None:
            raise self._embed_error
        return [deterministic_vector(text, self._embedding_dimensions) for text in texts]

    async def usage(
        self,
        session: object = None,
        *,
        since: datetime | None = None,
        call_name: str | None = None,
    ) -> UsageSummary:
        rows = [
            UsageRow(
                call_name=call.name,
                day=datetime.now(UTC).date(),
                outcome="ok",
                call_count=1,
                input_tokens=0,
                cached_read_tokens=0,
                output_tokens=0,
            )
            for call in self.calls
            if call_name is None or call.name == call_name
        ]
        return UsageSummary(
            rows=rows,
            total_calls=len(rows),
            total_input_tokens=0,
            total_output_tokens=0,
        )
