"""Response citations -> our Citation type."""

from typing import Any

from app.retrieval.types import Chunk, Citation


def extract_citations(content_blocks: list[Any], chunks: list[Chunk]) -> list[Citation]:
    """Map the API's citation objects back onto the chunks we sent."""
    citations: list[Citation] = []
    for block in content_blocks:
        raw = _get(block, "citations") or []
        for c in raw:
            idx = _get(c, "document_index")
            if idx is None or not (0 <= idx < len(chunks)):
                continue
            chunk = chunks[idx]
            citations.append(
                Citation(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=chunk.document_title,
                    uri=chunk.uri,
                    locator=chunk.locator,
                    cited_text=_get(c, "cited_text") or "",
                )
            )
    return citations


def answer_text(content_blocks: list[Any]) -> str:
    """Concatenate the text blocks of a response."""
    parts = []
    for block in content_blocks:
        if _get(block, "type") == "text":
            parts.append(_get(block, "text") or "")
    return "".join(parts)


def deep_link(citation: Citation, api_base: str = "") -> str:
    """Build the UI link for a citation from its locator."""
    loc = citation.locator or {}
    if "page" in loc:
        return f"{citation.uri}#page={loc['page']}"
    if "anchor" in loc:
        anchor = str(loc["anchor"]).lstrip("#")
        return f"{citation.uri}#{anchor}"
    return citation.uri


def _get(obj: Any, key: str) -> Any:
    """Content blocks arrive as SDK objects or dicts depending on the call path."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
