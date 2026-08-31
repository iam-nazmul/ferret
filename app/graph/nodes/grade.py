"""Binary sufficiency grade. Drives the single retry edge."""

from app.graph.state import State
from app.llm.client import get_client
from app.llm.models import GRADE_MODEL
from app.llm.prompts import GRADE_PROMPT
from app.logging import get_logger
from app.metrics import query_latency

log = get_logger(__name__)

_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "sufficient": {"type": "boolean"},
    },
    "required": ["reasoning", "sufficient"],
    "additionalProperties": False,
}


async def grade(state: State) -> dict:
    chunks = state.get("chunks", [])
    if not chunks:
        return {"sufficient": False}

    excerpts = "\n\n---\n\n".join(
        f"[{i}] {' > '.join(c.heading_path)}\n{c.text[:1500]}" for i, c in enumerate(chunks)
    )
    try:
        with query_latency.labels(stage="grade").time():
            result = await get_client().structured(
                model=GRADE_MODEL,
                system=GRADE_PROMPT,
                user=f"QUESTION: {state.get('question', '')}\n\nEXCERPTS:\n{excerpts}",
                schema=_SCHEMA,
                max_tokens=600,
            )
        sufficient = bool(result.get("sufficient", True))
    except Exception as exc:
        # Degrade toward answering: a grader outage shouldn't block a usable answer.
        log.warning("grade_failed", error=str(exc), assuming="sufficient")
        sufficient = True

    log.info("graded", sufficient=sufficient, retry_count=state.get("retry_count", 0))
    return {"sufficient": sufficient}
