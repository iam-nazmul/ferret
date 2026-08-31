"""Shared fixtures.

No test hits the Anthropic or OpenAI API — the suite must run offline and cost nothing.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from app.retrieval.types import Chunk


@dataclass
class FakeLLMResponse:
    content: list[Any]
    stop_reason: str | None = "end_turn"
    refusal_category: str | None = None
    input_tokens: int = 100
    output_tokens: int = 50
    cache_read_tokens: int = 80

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class FakeLLM:
    """Deterministic canned responses, recording what it was called with."""

    def __init__(self, answer: str = "The refund window is 30 days.", citations: list | None = None):
        self.answer = answer
        self.citations = citations if citations is not None else [{"document_index": 0, "cited_text": "30 days"}]
        self.calls: list[dict] = []
        self.structured_result: dict = {"sufficient": True, "reasoning": "ok"}

    async def answer_call(self, content, **kwargs):
        self.calls.append({"content": content, **kwargs})
        return FakeLLMResponse(
            content=[{"type": "text", "text": self.answer, "citations": self.citations}]
        )

    # Matches LLMClient's surface.
    async def answer(self, content, **kwargs):
        return await self.answer_call(content, **kwargs)

    async def structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.structured_result


class FakeReranker:
    """Identity reranker — keeps input order, assigns descending scores."""

    def __init__(self, fail: bool = False):
        self.fail = fail

    async def rerank(self, query: str, chunks: list[Chunk], top_k: int | None = None) -> list[Chunk]:
        """See `Reranker.rerank`."""
        if self.fail:
            from app.metrics import reranker_fallbacks

            reranker_fallbacks.inc()
            return chunks[: (top_k or 8)]
        for i, c in enumerate(chunks):
            c.rerank_score = 1.0 - i * 0.01
        return chunks[: (top_k or 8)]


class FakeRetriever:
    """`Retriever` returning canned chunks and recording its calls."""

    def __init__(self, chunks: list[Chunk] | None = None):
        self.chunks = chunks or []
        self.calls: list[dict] = []

    async def retrieve(self, query, user_groups, filters=None, limit=None):
        """See `Retriever.retrieve`."""
        self.calls.append({"query": query, "user_groups": user_groups, "filters": filters})
        return list(self.chunks)


def make_chunk(
    text: str = "The refund window is 30 days from the invoice date.",
    *,
    heading_path: list[str] | None = None,
    uri: str = "s3://docs/refund-policy.pdf",
    title: str = "Refund Policy",
    page: int = 3,
    score: float = 0.9,
) -> Chunk:
    return Chunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        text=text,
        locator={"page": page, "bbox": [0, 0, 100, 20]},
        heading_path=heading_path or ["Billing", "Refunds"],
        uri=uri,
        document_title=title,
        score=score,
    )


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_reranker():
    return FakeReranker()


@pytest.fixture
def chunk():
    return make_chunk()
