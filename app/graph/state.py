"""The contract between graph nodes.

Nodes are pure functions of state returning partial updates. Everything here must be
JSON-serializable — the checkpointer persists it.
"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages

from app.retrieval.types import Chunk, Citation, RetrievalFilters


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]

    # Set by the API layer, read-only below it. No node may widen user_groups.
    user_id: str
    user_groups: frozenset[str]
    filters: RetrievalFilters | None

    question: str
    is_multi_hop: bool
    sub_queries: list[str]

    candidates: list[Chunk]   # post-fusion, pre-rerank
    chunks: list[Chunk]       # post-rerank — what generation sees

    memories: list[str]
    sufficient: bool
    retry_count: int

    answer: str
    citations: list[Citation]
    groundedness_violation: bool
    refusal_category: str | None
    usage: dict[str, Any]


def initial_state(
    question: str,
    user_id: str,
    user_groups: frozenset[str],
    filters: RetrievalFilters | None = None,
) -> State:
    return State(
        messages=[HumanMessage(content=question)],
        question=question,
        user_id=user_id,
        user_groups=user_groups,
        filters=filters,
        sub_queries=[],
        candidates=[],
        chunks=[],
        memories=[],
        retry_count=0,
        groundedness_violation=False,
    )
