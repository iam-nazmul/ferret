"""Short-term memory: LangGraph checkpointer, keyed by thread_id.

Holds the full message history plus graph state. Everything stored must be
JSON-serializable.
"""

from contextlib import asynccontextmanager

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def get_checkpointer(in_memory: bool = False):
    """Checkpointer lifecycle. Use in_memory=True in tests."""
    if in_memory:
        yield InMemorySaver()
        return
    async with AsyncPostgresSaver.from_conn_string(settings.pg_conninfo) as cp:
        await cp.setup()  # idempotent; creates the checkpoint tables if missing
        yield cp


def summarize_if_needed(
    messages: list[AnyMessage], threshold: int | None = None
) -> list[AnyMessage] | None:
    """Collapse the older span of a long thread into one system note.

    Returns None when no summarization is needed. Without this, context cost grows
    without bound on long threads.
    """
    limit = threshold or settings.thread_summarize_after
    if len(messages) <= limit:
        return None

    keep = limit // 2
    older, recent = messages[:-keep], messages[-keep:]
    lines = []
    for m in older:
        role = getattr(m, "type", "message")
        content = str(getattr(m, "content", ""))[:200]
        lines.append(f"{role}: {content}")
    note = SystemMessage(
        content="Earlier in this conversation:\n" + "\n".join(lines[-40:])
    )
    log.info("thread_summarized", collapsed=len(older), kept=len(recent))
    return [note, *recent]
