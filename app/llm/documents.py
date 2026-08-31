"""Chunk -> Anthropic document content block.

Each chunk is its own document block so the API's citation locators map back to our
chunks by index. Citations must be enabled on all blocks or none.
"""

import json
from typing import Any

from app.retrieval.types import Chunk


def to_document_block(chunk: Chunk) -> dict[str, Any]:
    title = chunk.document_title or chunk.uri
    if chunk.heading_path:
        title = f"{title} — {' > '.join(chunk.heading_path)}"
    return {
        "type": "document",
        "source": {
            "type": "content",
            "content": [{"type": "text", "text": chunk.text}],
        },
        "title": title[:200],
        "context": json.dumps({"uri": chunk.uri, "locator": chunk.locator}),
        "citations": {"enabled": True},
    }


def pack_context(chunks: list[Chunk], question: str, memories: str = "") -> list[dict[str, Any]]:
    """Build the user message content: documents first, then the question."""
    content: list[dict[str, Any]] = [to_document_block(c) for c in chunks]
    prefix = f"{memories}\n\n" if memories else ""
    content.append({"type": "text", "text": f"{prefix}Question: {question}"})
    return content
