"""Request/response models.

NOTE: no schema here carries user_id, groups, or any ACL input. If a caller could pass
it, a caller could forge it — those come from the verified JWT via Principal.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class ChatFilters(BaseModel):
    doc_type: list[str] = Field(default_factory=list)
    effective_after: date | None = None
    effective_before: date | None = None


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    filters: ChatFilters | None = None


class SourceRef(BaseModel):
    chunk_id: str
    document_id: str
    title: str | None
    uri: str
    heading_path: list[str]
    locator: dict[str, Any]
    rerank_score: float | None = None
    snippet: str


class CitationRef(BaseModel):
    document_id: str
    title: str | None
    uri: str
    locator: dict[str, Any]
    cited_text: str
    link: str


class FeedbackRequest(BaseModel):
    run_id: str
    thread_id: str
    score: int = Field(ge=-1, le=1)
    comment: str | None = Field(default=None, max_length=2000)


class MemoryItem(BaseModel):
    id: str
    data: str


class ThreadSummary(BaseModel):
    thread_id: str
    preview: str
    updated_at: str | None = None


class SourceStatus(BaseModel):
    id: str
    kind: str
    uri: str
    enabled: bool
    last_run_at: str | None
    document_count: int
    failed_count: int


class FailedDocument(BaseModel):
    uri: str
    error: str | None
    indexed_at: str | None
