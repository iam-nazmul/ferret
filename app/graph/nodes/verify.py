"""Citation coverage check.

Never blocks the answer — it flags. A hard block turns a degraded answer into an outage.
"""

import re

from langchain_core.messages import AIMessage

from app.graph.state import State
from app.logging import get_logger
from app.metrics import groundedness_violations

log = get_logger(__name__)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")

# Meta and hedging sentences make no checkable claim, so they need no citation.
# Everything else is treated as a claim: this defaults toward flagging, which is the
# safe direction — a false positive is a visible warning the reader can dismiss, while
# a false negative ships an uncited claim silently.
_HEDGE = re.compile(
    r"^\s*(i |i'|we |we'|here|this |that |these |those |the following|note that|"
    r"in (short|summary)|based on|according to the (documents|sources)|let me|"
    r"to summarize|if you|you (can|may|might|should)|it (may|might) )",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text or "") if s.strip()]


def is_factual(sentence: str) -> bool:
    """A sentence that asserts something checkable against the corpus.

    Deliberately permissive — see the note on _HEDGE. Requiring a positive signal
    (a number, a copula) missed claims like "Enterprise customers also get priority
    support", which is exactly the kind of unsupported assertion this check exists for.
    """
    if len(sentence) < 25:
        return False
    return not _HEDGE.match(sentence)


def uncited_factual_sentences(answer: str, cited_texts: list[str]) -> list[str]:
    """Factual sentences with no overlapping citation."""
    if not answer:
        return []
    cited_blob = " ".join(cited_texts).lower()
    uncited = []
    for sentence in split_sentences(answer):
        if not is_factual(sentence):
            continue
        if not _overlaps(sentence.lower(), cited_blob):
            uncited.append(sentence)
    return uncited


def _overlaps(sentence: str, cited_blob: str, threshold: float = 0.35) -> bool:
    """Content-word overlap between a sentence and the cited spans."""
    if not cited_blob:
        return False
    words = {w for w in re.findall(r"\w+", sentence) if len(w) > 3}
    if not words:
        return True
    hits = sum(1 for w in words if w in cited_blob)
    return hits / len(words) >= threshold


async def verify(state: State) -> dict:
    answer = state.get("answer", "")
    citations = state.get("citations", [])
    uncited = uncited_factual_sentences(answer, [c.cited_text for c in citations])

    if uncited:
        groundedness_violations.inc()
        log.warning("groundedness_violation", uncited_count=len(uncited))

    return {
        "groundedness_violation": bool(uncited),
        "messages": [AIMessage(content=answer)],
    }
