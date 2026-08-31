"""Inline citation markers."""

import re

import streamlit as st


def render_answer(answer: str, citations: list[dict], violation: bool = False) -> None:
    if violation:
        st.warning(
            "Parts of this answer aren't backed by a citation. Verify anything you act on.",
            icon="⚠️",
        )

    st.markdown(_with_markers(answer, citations))

    if citations:
        with st.expander(f"{len(citations)} citations"):
            for i, c in enumerate(citations, 1):
                title = c.get("title") or c.get("uri", "")
                st.markdown(f"**[{i}]** [{title}]({c.get('link', c.get('uri', '#'))})")
                if c.get("cited_text"):
                    st.caption(f"“{c['cited_text'][:400]}”")


def _with_markers(answer: str, citations: list[dict]) -> str:
    """Attach a marker to the sentence each citation's text overlaps."""
    if not citations:
        return answer

    sentences = re.split(r"(?<=[.!?])(\s+)", answer)
    out: list[str] = []
    used: set[int] = set()

    for part in sentences:
        out.append(part)
        if not part.strip() or part.isspace():
            continue
        lowered = part.lower()
        markers = []
        for i, c in enumerate(citations, 1):
            if i in used:
                continue
            cited = (c.get("cited_text") or "").lower()
            if cited and _overlaps(lowered, cited):
                markers.append(i)
                used.add(i)
        if markers:
            out.append(" " + "".join(f"<sup>[{m}]</sup>" for m in markers))

    tail = [i for i in range(1, len(citations) + 1) if i not in used]
    rendered = "".join(out)
    if tail:
        rendered += " " + "".join(f"<sup>[{i}]</sup>" for i in tail)
    return rendered


def _overlaps(sentence: str, cited: str, threshold: float = 0.4) -> bool:
    words = {w for w in re.findall(r"\w+", cited) if len(w) > 3}
    if not words:
        return False
    hits = sum(1 for w in words if w in sentence)
    return hits / len(words) >= threshold
