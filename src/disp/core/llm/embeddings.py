"""Embedding providers — a separate vendor from the LLM client (M19-llm.md
§7). Anthropic publishes no embeddings endpoint, so this talks to a
different vendor, with a different key, base URL, and failure mode from
every other method on LLMFacade.
"""

import asyncio
import hashlib
from typing import Protocol

import httpx

VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...  # pragma: no cover


class VoyageEmbeddingProvider:
    def __init__(self, *, api_key: str, model: str, http_client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._model = model
        self._http_client = http_client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._http_client.post(
            VOYAGE_API_URL,
            json={"input": texts, "model": self._model},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]


class LocalEmbeddingProvider:
    """sentence-transformers, behind the optional `local-embeddings` extra
    (pyproject.toml). No network, no key, no per-token cost — a meaningfully
    worse retrieval quality and a large image, for deployments that will not
    send text to a third party."""

    def __init__(self, *, model: str) -> None:
        # Deferred: only imported when DISP_EMBEDDING_PROVIDER=local, behind
        # the optional `local-embeddings` extra (pyproject.toml) — not
        # installed by default, so no type stubs are available either.
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        self._model = SentenceTransformer(model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await asyncio.to_thread(self._model.encode, texts)
        return [vector.tolist() for vector in vectors]


def deterministic_vector(text: str, dimensions: int) -> list[float]:
    """Hash-derived, reproducible vector — used by FakeLLM (fake.py) so
    embedding-similarity assertions are reproducible across test runs while
    still exercising the dimension invariant (L7)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    while len(values) < dimensions:
        digest = hashlib.sha256(digest).digest()
        values.extend(byte / 255.0 for byte in digest)
    return values[:dimensions]
