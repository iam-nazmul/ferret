"""Types crossing ingestion stage boundaries."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Discovered:
    """One candidate document from a source."""

    uri: str
    metadata: dict[str, Any] = field(default_factory=dict)
    acl_groups: list[str] | None = None  # overrides the source default when set


@dataclass(slots=True)
class Fetched:
    uri: str
    content: bytes
    content_type: str
    etag: str | None = None
    unchanged: bool = False


@dataclass(slots=True)
class ParsedBlock:
    """A positioned span of text. `locator` is what makes a citation clickable."""

    text: str
    locator: dict[str, Any]
    heading_path: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Parsed:
    title: str | None
    blocks: list[ParsedBlock]
    page_count: int | None = None


@dataclass(slots=True)
class PreparedChunk:
    text: str
    locator: dict[str, Any]
    heading_path: list[str]
    token_count: int
    ordinal: int
