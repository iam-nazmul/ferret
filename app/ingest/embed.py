"""Batched embedding with backoff. Shares config with retrieval via app.config."""

import asyncio

from tenacity import retry, stop_after_attempt, wait_exponential

from app.logging import get_logger
from app.retrieval.embed import embed_batch

log = get_logger(__name__)

BATCH_SIZE = 100


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=2, max=60))
async def _embed_one_batch(texts: list[str]) -> list[list[float]]:
    return await embed_batch(texts)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vectors.extend(await _embed_one_batch(batch))
        if i + BATCH_SIZE < len(texts):
            await asyncio.sleep(0.05)
    log.info("embedded", count=len(vectors))
    return vectors
