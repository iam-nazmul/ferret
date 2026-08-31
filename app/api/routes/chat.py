"""The chat endpoint — the only streaming route."""

import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api import sse
from app.api.deps import CurrentUser, get_graph, get_store
from app.api.ratelimit import limiter
from app.api.schemas import ChatRequest
from app.graph.state import initial_state
from app.llm.citations import deep_link
from app.logging import get_logger
from app.memory.extraction import extract_and_store
from app.memory.store import search_memories
from app.metrics import active_requests, query_latency
from app.retrieval.types import RetrievalFilters

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat")
async def chat(
    body: ChatRequest,
    principal: CurrentUser,
    graph=Depends(get_graph),
    store=Depends(get_store),
) -> StreamingResponse:
    limiter.check(principal.user_id)
    thread_id = body.thread_id or str(uuid.uuid4())

    return StreamingResponse(
        _stream(body, principal, graph, store, thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # proxies must not buffer SSE
            "X-Thread-Id": thread_id,
        },
    )


async def _stream(body, principal, graph, store, thread_id: str) -> AsyncIterator[str]:
    """StreamingResponse swallows exceptions after the first byte — convert them here."""
    started = time.monotonic()
    limiter.acquire(principal.user_id)
    active_requests.inc()
    run_id = str(uuid.uuid4())

    try:
        yield sse.status("retrieving")

        memories = []
        if store is not None:
            try:
                memories = await search_memories(store, principal.user_id, body.message)
            except Exception as exc:
                log.warning("memory_search_failed", error=str(exc))

        filters = None
        if body.filters:
            filters = RetrievalFilters(
                doc_type=body.filters.doc_type,
                effective_after=body.filters.effective_after,
                effective_before=body.filters.effective_before,
            )

        state = initial_state(
            body.message,
            user_id=principal.user_id,
            user_groups=principal.groups,
            filters=filters,
        )
        state["memories"] = memories

        config = {"configurable": {"thread_id": thread_id}}

        with query_latency.labels(stage="total").time():
            result = await graph.ainvoke(state, config)

        chunks = result.get("chunks", [])
        yield sse.sources(
            [
                {
                    "chunk_id": str(c.id),
                    "document_id": str(c.document_id),
                    "title": c.document_title,
                    "uri": c.uri,
                    "heading_path": c.heading_path,
                    "locator": c.locator,
                    "rerank_score": c.rerank_score,
                    "snippet": c.text[:300],
                }
                for c in chunks
            ]
        )

        yield sse.status("generating")
        answer = result.get("answer", "")
        # The graph produces the answer whole; chunk it for a responsive UI.
        for i in range(0, len(answer), 24):
            yield sse.token(answer[i : i + 24])

        for c in result.get("citations", []):
            yield sse.citation(
                {
                    "document_id": str(c.document_id),
                    "title": c.document_title,
                    "uri": c.uri,
                    "locator": c.locator,
                    "cited_text": c.cited_text,
                    "link": deep_link(c),
                }
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        yield sse.done(
            run_id,
            result.get("usage", {}),
            latency_ms,
            bool(result.get("groundedness_violation")),
        )

        if store is not None and answer:
            try:
                await extract_and_store(
                    store, principal.user_id, thread_id, body.message, answer
                )
            except Exception as exc:
                log.warning("extraction_failed", error=str(exc))

    except Exception as exc:
        log.exception("chat_failed", error=str(exc))
        yield sse.error("Something went wrong answering that. The error has been logged.")
    finally:
        limiter.release(principal.user_id)
        active_requests.dec()
