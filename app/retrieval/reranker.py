"""Cross-encoder reranker client."""

import httpx

from app.config import settings
from app.logging import get_logger
from app.metrics import reranker_fallbacks
from app.retrieval.types import Chunk

log = get_logger(__name__)


class Reranker:
    def __init__(self, base_url: str | None = None, timeout: float = 2.0) -> None:
        self._url = (base_url or settings.reranker_url).rstrip("/")
        self._timeout = timeout

    async def rerank(self, query: str, chunks: list[Chunk], top_k: int | None = None) -> list[Chunk]:
        k = top_k or settings.top_k
        if not chunks:
            return []
        if len(chunks) <= k:
            return chunks

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._url}/rerank",
                    json={"query": query, "documents": [c.text for c in chunks], "top_k": k},
                )
                resp.raise_for_status()
                results = resp.json()["results"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            reranker_fallbacks.inc()
            log.warning("reranker_unavailable", error=str(exc), fallback="rrf_order")
            return chunks[:k]

        ranked: list[Chunk] = []
        for item in results:
            idx = item["index"]
            if 0 <= idx < len(chunks):
                chunk = chunks[idx]
                chunk.rerank_score = float(item["score"])
                ranked.append(chunk)
        return ranked[:k] if ranked else chunks[:k]
