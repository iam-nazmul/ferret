"""Graph topology. All edges live here — never as branching returns buried in nodes."""

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.graph.nodes.decompose import decompose
from app.graph.nodes.generate import generate
from app.graph.nodes.grade import grade
from app.graph.nodes.rerank import make_rerank_node
from app.graph.nodes.retrieve import make_retrieve_node
from app.graph.nodes.route import route
from app.graph.nodes.verify import verify
from app.graph.state import State
from app.logging import get_logger
from app.retrieval.base import Retriever
from app.retrieval.reranker import Reranker

log = get_logger(__name__)


def _after_route(state: State) -> str:
    return "decompose" if state.get("is_multi_hop") else "retrieve"


def _after_grade(state: State) -> str:
    """One retry, then answer with what we have (SPEC §8.5)."""
    if state.get("sufficient", True):
        return "generate"
    if state.get("retry_count", 0) >= settings.max_retries:
        return "generate"
    return "rewrite"


async def rewrite(state: State) -> dict:
    """Widen the query for one more retrieval pass."""
    question = state.get("question", "")
    headings = {h for c in state.get("candidates", [])[:5] for h in c.heading_path}
    widened = f"{question} {' '.join(sorted(headings))}".strip() if headings else question
    return {"sub_queries": [widened], "retry_count": state.get("retry_count", 0) + 1}


def build_graph(
    retriever: Retriever,
    reranker: Reranker | None = None,
    checkpointer: Any = None,
    store: Any = None,
):
    reranker = reranker or Reranker()

    builder = StateGraph(State)
    builder.add_node("route", route)
    builder.add_node("decompose", decompose)
    builder.add_node("retrieve", make_retrieve_node(retriever))
    builder.add_node("rerank", make_rerank_node(reranker))
    builder.add_node("grade", grade)
    builder.add_node("rewrite", rewrite)
    builder.add_node("generate", generate)
    builder.add_node("verify", verify)

    builder.add_edge(START, "route")
    builder.add_conditional_edges("route", _after_route, ["decompose", "retrieve"])
    builder.add_edge("decompose", "retrieve")
    builder.add_edge("retrieve", "rerank")
    builder.add_edge("rerank", "grade")
    builder.add_conditional_edges("grade", _after_grade, ["generate", "rewrite"])
    builder.add_edge("rewrite", "retrieve")
    builder.add_edge("generate", "verify")
    builder.add_edge("verify", END)

    return builder.compile(checkpointer=checkpointer, store=store)
