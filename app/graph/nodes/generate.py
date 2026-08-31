"""Generation with API-guaranteed citations."""

from app.config import settings
from app.graph.state import State
from app.llm.cache import memory_block
from app.llm.citations import answer_text, extract_citations
from app.llm.client import get_client
from app.llm.documents import pack_context
from app.llm.models import EFFORT_DEFAULT, EFFORT_SYNTHESIS
from app.logging import get_logger
from app.metrics import query_latency

log = get_logger(__name__)

INSUFFICIENT_ANSWER = (
    "I couldn't find enough information in the indexed documents to answer that "
    "confidently. Here is what I did find, which may be adjacent to what you need:"
)


async def generate(state: State) -> dict:
    chunks = state.get("chunks", [])

    if not chunks:
        return {
            "answer": (
                "I couldn't find anything in the documents you have access to that "
                "addresses that question."
            ),
            "citations": [],
        }

    if not state.get("sufficient", True) and state.get("retry_count", 0) >= settings.max_retries:
        listing = "\n".join(
            f"- {c.document_title or c.uri}"
            + (f" — {' > '.join(c.heading_path)}" if c.heading_path else "")
            for c in chunks[:5]
        )
        return {"answer": f"{INSUFFICIENT_ANSWER}\n{listing}", "citations": []}

    content = pack_context(
        chunks, state.get("question", ""), memory_block(state.get("memories", []))
    )
    effort = EFFORT_SYNTHESIS if state.get("is_multi_hop") else EFFORT_DEFAULT

    with query_latency.labels(stage="generate").time():
        resp = await get_client().answer(content, effort=effort)

    if resp.refused:
        return {
            "answer": (
                "I can't answer that one. The request was declined by a safety filter"
                + (f" ({resp.refusal_category})." if resp.refusal_category else ".")
            ),
            "citations": [],
            "refusal_category": resp.refusal_category,
        }

    return {
        "answer": answer_text(resp.content),
        "citations": extract_citations(resp.content, chunks),
        "usage": {
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "cache_read_tokens": resp.cache_read_tokens,
        },
    }
