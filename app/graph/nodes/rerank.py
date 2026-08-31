"""Cross-encoder rerank, 30 -> 8."""

from app.graph.state import State
from app.logging import get_logger
from app.metrics import query_latency
from app.retrieval.reranker import Reranker

log = get_logger(__name__)


def make_rerank_node(reranker: Reranker):
    async def rerank(state: State) -> dict:
        candidates = state.get("candidates", [])
        if not candidates:
            return {"chunks": []}

        with query_latency.labels(stage="rerank").time():
            chunks = await reranker.rerank(state.get("question", ""), candidates)

        log.info(
            "reranked",
            kept=len(chunks),
            chunk_ids=[str(c.id) for c in chunks],
            scores=[c.rerank_score for c in chunks],
        )
        return {"chunks": chunks}

    return rerank
