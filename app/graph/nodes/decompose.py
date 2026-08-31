"""Multi-hop -> 2-4 self-contained sub-queries."""

from app.graph.state import State
from app.llm.client import get_client
from app.llm.models import GRADE_MODEL
from app.llm.prompts import DECOMPOSE_PROMPT
from app.logging import get_logger

log = get_logger(__name__)

_SCHEMA = {
    "type": "object",
    "properties": {
        "sub_queries": {"type": "array", "items": {"type": "string"}, "maxItems": 4}
    },
    "required": ["sub_queries"],
    "additionalProperties": False,
}


async def decompose(state: State) -> dict:
    question = state.get("question", "")
    try:
        result = await get_client().structured(
            model=GRADE_MODEL,
            system=DECOMPOSE_PROMPT,
            user=question,
            schema=_SCHEMA,
            max_tokens=800,
        )
        subs = [s for s in (result.get("sub_queries") or []) if isinstance(s, str) and s.strip()]
    except Exception as exc:
        log.warning("decompose_failed", error=str(exc))
        subs = []

    subs = subs[:4] or [question]
    log.info("decomposed", count=len(subs))
    return {"sub_queries": subs}
