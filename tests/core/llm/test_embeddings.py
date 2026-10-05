"""Embeddings — a separate provider from generation (M19-llm.md §7, L7).

No network: VoyageEmbeddingProvider is exercised against an httpx
MockTransport, never a real endpoint. LocalEmbeddingProvider is exercised
against a fake `sentence_transformers` module injected into sys.modules,
never the real (large, optional) dependency.
"""

import sys
import types

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from disp.core.config import get_settings
from disp.core.llm import LLMFacade
from disp.core.llm.embeddings import (
    LocalEmbeddingProvider,
    VoyageEmbeddingProvider,
    deterministic_vector,
)
from disp.core.llm.errors import LLMInvalidOutput, LLMNotConfigured


def test_deterministic_vector_is_reproducible_and_correct_length() -> None:
    first = deterministic_vector("hello", 32)
    second = deterministic_vector("hello", 32)
    assert first == second
    assert len(first) == 32
    assert all(0.0 <= value <= 1.0 for value in first)


def test_deterministic_vector_differs_by_input() -> None:
    assert deterministic_vector("hello", 16) != deterministic_vector("world", 16)


async def test_voyage_provider_returns_embeddings_via_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.voyageai.com/v1/embeddings")
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = VoyageEmbeddingProvider(
        api_key="test-key", model="voyage-3", http_client=http_client
    )

    vectors = await provider.embed(["hello"])

    assert vectors == [[0.1, 0.2, 0.3]]


class _FakeVector:
    def __init__(self, values: list[float]) -> None:
        self._values = values

    def tolist(self) -> list[float]:
        return self._values


class _FakeSentenceTransformer:
    def __init__(self, model: str) -> None:
        self.model = model

    def encode(self, texts: list[str]) -> list[_FakeVector]:
        return [_FakeVector([float(len(t)), 0.0]) for t in texts]


@pytest.fixture
def fake_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)


async def test_local_embedding_provider_via_fake_module(
    fake_sentence_transformers: None,
) -> None:
    provider = LocalEmbeddingProvider(model="fake-model")
    vectors = await provider.embed(["hi", "longer text"])
    assert vectors == [[2.0, 0.0], [11.0, 0.0]]


async def test_facade_builds_local_embedding_provider(
    fake_sentence_transformers: None,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    from disp.core.config import Settings

    data = get_settings().model_dump()
    data.update(
        embedding_enabled=True,
        embedding_provider="local",
        embedding_model="fake-model",
        embedding_dimensions=2,
    )
    settings = Settings(**data)

    facade = LLMFacade.from_settings(settings, session_maker)

    assert isinstance(facade._embedding_provider, LocalEmbeddingProvider)  # type: ignore[attr-defined]
    vectors = await facade.embed(["hi", "world"])
    assert vectors == [[2.0, 0.0], [5.0, 0.0]]


async def test_facade_embed_raises_not_configured_when_disabled() -> None:
    settings = get_settings().model_copy(update={"embedding_enabled": False})
    facade = LLMFacade.from_settings(settings, None)  # type: ignore[arg-type]
    with pytest.raises(LLMNotConfigured):
        await facade.embed(["hello"])


async def test_facade_embed_rejects_wrong_dimension_vector(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    base = get_settings()
    data = base.model_dump()
    data.update(
        embedding_enabled=True,
        embedding_provider="voyage",
        embedding_api_key=SecretStr("test-key"),
        embedding_dimensions=1024,
    )
    from disp.core.config import Settings

    settings = Settings(**data)
    facade = LLMFacade.from_settings(settings, session_maker)

    class _WrongDimensionProvider:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]  # 2 dims, not 1024

    facade._embedding_provider = _WrongDimensionProvider()  # type: ignore[attr-defined]

    with pytest.raises(LLMInvalidOutput):
        await facade.embed(["hello"])
