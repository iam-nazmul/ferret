"""Retrieval, one pass per sub-query, unioned."""

import asyncio

from app.graph.state import State
from app.logging import get_logger
from app.metrics import query_latency
from app.retrieval.base import Retriever
from app.retrieval.hybrid import dedupe_by_id
from app.retrieval.types import Chunk

log = get_logger(__name__)


def make_retrieve_node(retriever: Retriever):
    async def retrieve(state: State) -> dict:
        queries = state.get("sub_queries") or [state.get("question", "")]
        groups = state.get("user_groups", frozenset())
        filters = state.get("filters")

        with query_latency.labels(stage="retrieve").time():
            results: list[list[Chunk]] = await asyncio.gather(
                *(retriever.retrieve(q, groups, filters) for q in queries)
            )

        candidates = dedupe_by_id(results)
        log.info("retrieve_node", queries=len(queries), candidates=len(candidates))
        return {"candidates": candidates}

    return retrieve
