"""Query embedding."""

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


@lru_cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key or None)


async def embed_query(text: str) -> list[float]:
    resp = await _client().embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dims,
    )
    return list(resp.data[0].embedding)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = await _client().embeddings.create(
        model=settings.embedding_model,
        input=texts,
        dimensions=settings.embedding_dims,
    )
    return [list(d.embedding) for d in sorted(resp.data, key=lambda d: d.index)]
