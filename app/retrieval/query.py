"""Query text sanitization for the sparse side.

`websearch_to_tsquery` raises on some punctuation. Sanitizing here is correct; wrapping
the whole search in try/except and returning empty is not — that turns a parse bug into
"Ferret knows nothing".
"""

import re

_UNSAFE = re.compile(r"[<>()\[\]{}!&|:*\\\"']")
_WS = re.compile(r"\s+")


def sanitize_tsquery(text: str) -> str:
    """Make a string safe for websearch_to_tsquery, preserving useful terms."""
    cleaned = _UNSAFE.sub(" ", text)
    cleaned = cleaned.replace("-", " ")
    cleaned = _WS.sub(" ", cleaned).strip()
    return cleaned[:1000]
