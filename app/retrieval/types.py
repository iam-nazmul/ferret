"""Types crossing the retrieval boundary. Kept dependency-free so anything can import them."""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class Chunk:
    id: uuid.UUID
    document_id: uuid.UUID
    text: str
    locator: dict[str, Any]
    heading_path: list[str]
    uri: str
    document_title: str | None = None
    ordinal: int = 0
    score: float = 0.0
    rerank_score: float | None = None


@dataclass(slots=True)
class Citation:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str | None
    uri: str
    locator: dict[str, Any]
    cited_text: str


@dataclass(slots=True)
class RetrievalFilters:
    doc_type: list[str] = field(default_factory=list)
    effective_after: date | None = None
    effective_before: date | None = None

    def is_empty(self) -> bool:
        return not self.doc_type and not self.effective_after and not self.effective_before
