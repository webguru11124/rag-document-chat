from collections.abc import Iterator
from typing import Protocol

import openai
from google import genai

from app.providers.catalog import GOOGLE, MOCK, OPENAI, EmbeddingModel, embedding_model
from app.providers.errors import ProviderError, translate
from app.providers.keys import ApiKeys

BATCH_SIZE = 64


class Embedder(Protocol):
    model: EmbeddingModel

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


def batches(items: list[str], size: int = BATCH_SIZE) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class OpenAIEmbedder:
    def __init__(self, model: EmbeddingModel, api_key: str, client: openai.AsyncOpenAI | None = None):
        self.model = model
        self.client = client or openai.AsyncOpenAI(api_key=api_key)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            for batch in batches(texts):
                response = await self.client.embeddings.create(model=self.model.id, input=batch)
                vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        except Exception as exc:
            raise translate(exc, "OpenAI") from exc
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]


class GoogleEmbedder:
    def __init__(self, model: EmbeddingModel, api_key: str, client: genai.Client | None = None):
        self.model = model
        self.client = client or genai.Client(api_key=api_key)

    async def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            for batch in batches(texts):
                response = await self.client.aio.models.embed_content(
                    model=self.model.id,
                    contents=batch,
                    config={"task_type": task_type, "output_dimensionality": self.model.dimensions},
                )
                vectors.extend(list(embedding.values) for embedding in response.embeddings)
        except Exception as exc:
            raise translate(exc, "Google Gemini") from exc
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]


def get_embedder(provider: str, model_id: str, keys: ApiKeys, *, mock_enabled: bool) -> Embedder:
    model = embedding_model(provider, model_id)
    if model is None:
        raise ProviderError(f"Unknown embedding model '{model_id}' for provider '{provider}'.", 400)
    if provider == MOCK:
        if not mock_enabled:
            raise ProviderError("The mock provider is disabled on this server.", 400)
        from app.providers.mock import MockEmbedder

        return MockEmbedder(model)
    api_key = keys.for_provider(provider)
    if provider == OPENAI:
        return OpenAIEmbedder(model, api_key)
    if provider == GOOGLE:
        return GoogleEmbedder(model, api_key)
    raise ProviderError(f"Provider '{provider}' has no embedding models.", 400)
