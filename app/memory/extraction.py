"""End-of-turn extraction of durable user facts."""

from typing import Any

from app.llm.client import get_client
from app.llm.models import EXTRACT_MODEL
from app.llm.prompts import EXTRACT_PROMPT
from app.logging import get_logger
from app.memory.store import add_memory

log = get_logger(__name__)

_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Durable facts about the user. Empty when nothing lasting was said.",
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


async def extract_facts(user_message: str, assistant_message: str) -> list[str]:
    result = await get_client().structured(
        model=EXTRACT_MODEL,
        system=EXTRACT_PROMPT,
        user=f"USER: {user_message}\n\nASSISTANT: {assistant_message}",
        schema=_SCHEMA,
        max_tokens=1000,
    )
    facts = result.get("facts") or []
    return [f for f in facts if isinstance(f, str) and f.strip()]


async def extract_and_store(
    store: Any, user_id: str, thread_id: str, user_message: str, assistant_message: str
) -> int:
    try:
        facts = await extract_facts(user_message, assistant_message)
    except Exception as exc:  # extraction is best-effort; never fail the turn for it
        log.warning("extraction_failed", error=str(exc))
        return 0

    for fact in facts:
        await add_memory(store, user_id, fact, thread_id)
    return len(facts)
