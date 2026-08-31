"""The Retriever protocol. Swap implementations behind this, not by editing call sites."""

from typing import Protocol

from app.retrieval.types import Chunk, RetrievalFilters


class Retriever(Protocol):
    async def retrieve(
        self,
        query: str,
        user_groups: frozenset[str],
        filters: RetrievalFilters | None = None,
        limit: int | None = None,
    ) -> list[Chunk]:
        """Return authorized candidate chunks, best first.

        Implementations MUST enforce `user_groups` inside the query, not afterwards.
        """
        ...
