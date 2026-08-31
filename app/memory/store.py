"""Long-term memory: LangGraph store with semantic search.

There is NO ACL layer on the store — the namespace is the only isolation. Always
("memories", user_id), and never document content: that would be an unauthorized second
copy of the corpus outside the permission model.
"""

import uuid
from contextlib import asynccontextmanager
from typing import Any

from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


def namespace(user_id: str) -> tuple[str, str]:
    return ("memories", user_id)


@asynccontextmanager
async def get_store(in_memory: bool = False):
    if in_memory:
        yield InMemoryStore()
        return
    async with AsyncPostgresStore.from_conn_string(
        settings.pg_conninfo,
        index={"dims": settings.embedding_dims, "embed": f"openai:{settings.embedding_model}"},
    ) as store:
        await store.setup()  # idempotent; creates the store tables if missing
        yield store


async def search_memories(store: Any, user_id: str, query: str, limit: int | None = None) -> list[str]:
    """Semantic search over a user's memories. Empty query returns nothing useful — guard it."""
    if not query.strip():
        return []
    items = await store.asearch(
        namespace(user_id), query=query, limit=limit or settings.memory_search_limit
    )
    return [item.value["data"] for item in items if item.value.get("data")]


async def add_memory(store: Any, user_id: str, fact: str, thread_id: str = "") -> str:
    """Insert a fact, merging semantic near-duplicates rather than accumulating them."""
    existing = await store.asearch(namespace(user_id), query=fact, limit=3)
    for item in existing:
        if _near_duplicate(fact, item.value.get("data", "")):
            log.info("memory_duplicate_skipped", user_id=user_id)
            return str(item.key)

    key = str(uuid.uuid4())
    await store.aput(namespace(user_id), key, {"data": fact, "source_thread": thread_id})
    log.info("memory_added", user_id=user_id)
    return key


async def list_memories(store: Any, user_id: str) -> list[dict[str, Any]]:
    items = await store.asearch(namespace(user_id), limit=200)
    return [{"id": str(i.key), "data": i.value.get("data", "")} for i in items]


async def delete_memory(store: Any, user_id: str, key: str) -> None:
    """Real deletion, not a tombstone — this is the GDPR erasure path."""
    await store.adelete(namespace(user_id), key)
    log.info("memory_deleted", user_id=user_id)


async def delete_all_memories(store: Any, user_id: str) -> int:
    items = await store.asearch(namespace(user_id), limit=1000)
    for item in items:
        await store.adelete(namespace(user_id), item.key)
    return len(items)


def _near_duplicate(a: str, b: str, threshold: float = 0.85) -> bool:
    """Token-overlap duplicate check. Cheap, and good enough before an embedding round trip."""
    if not a or not b:
        return False
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold
