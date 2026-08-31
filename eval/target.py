"""The graph as an (inputs -> outputs) callable."""

import asyncio
import uuid
from typing import Any

from app.graph.build import build_graph
from app.graph.state import initial_state
from app.models.base import session_factory
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.reranker import Reranker


class _SessionRetriever:
    """`Retriever` that opens a session per call."""

    async def retrieve(self, query, user_groups, filters=None, limit=None):
        """See `Retriever.retrieve`."""
        async with session_factory() as session:
            return await HybridRetriever(session).retrieve(query, user_groups, filters, limit)


def make_target(user_groups: frozenset[str] = frozenset({"all"})):
    """Build the evaluate() target."""
    graph = build_graph(_SessionRetriever(), reranker=Reranker(), checkpointer=None, store=None)

    def target(inputs: dict) -> dict[str, Any]:
        question = inputs["question"]
        groups = frozenset(inputs.get("user_groups") or user_groups)
        state = initial_state(question, user_id="eval", user_groups=groups)
        # Distinct thread per example: evaluate() runs concurrently and a shared
        # thread bleeds memory between them.
        config = {"configurable": {"thread_id": f"eval-{uuid.uuid4()}"}}
        result = asyncio.run(graph.ainvoke(state, config))

        return {
            "answer": result.get("answer", ""),
            "refused": bool(result.get("refusal_category")),
            "groundedness_violation": bool(result.get("groundedness_violation")),
            "chunks": [
                {
                    "chunk_id": str(c.id),
                    "document_id": str(c.document_id),
                    "text": c.text,
                    "uri": c.uri,
                }
                for c in result.get("chunks", [])
            ],
            "citations": [
                {
                    "document_id": str(c.document_id),
                    "cited_text": c.cited_text,
                    "uri": c.uri,
                }
                for c in result.get("citations", [])
            ],
            "usage": result.get("usage", {}),
        }

    return target
