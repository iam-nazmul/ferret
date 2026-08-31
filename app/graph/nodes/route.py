"""Classify the question as simple or multi-hop."""

import re

from app.graph.state import State
from app.logging import get_logger

log = get_logger(__name__)

_MULTI_HOP_SIGNALS = re.compile(
    r"\b(compare|difference|differ|versus|vs\.?|both|each of|across|"
    r"and how|as well as|trend|over the last|between)\b",
    re.IGNORECASE,
)


async def route(state: State) -> dict:
    question = state.get("question", "")
    multi = bool(_MULTI_HOP_SIGNALS.search(question)) or question.count("?") > 1
    log.info("routed", multi_hop=multi)
    return {"is_multi_hop": multi}
