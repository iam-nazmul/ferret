"""Hybrid retrieval: dense + sparse, fused with RRF, in one round trip.

THE RULE: the ACL predicate lives in the innermost WHERE of both CTEs. Never fetch
broadly and filter in Python — unauthorized rows leaving the database are one refactor
away from being in a prompt. See .claude/skills/acl-audit.
"""

import uuid
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logging import get_logger
from app.metrics import retrieval_candidates
from app.retrieval.embed import embed_query
from app.retrieval.filters import build_filter_sql
from app.retrieval.query import sanitize_tsquery
from app.retrieval.types import Chunk, RetrievalFilters

log = get_logger(__name__)

HYBRID_SQL = """
WITH dense AS (
  SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> :qvec) AS rank
  FROM chunks c JOIN documents d ON d.id = c.document_id
  WHERE d.acl_groups && :user_groups AND d.status = 'indexed'{filters}
    AND c.embedding IS NOT NULL
  ORDER BY c.embedding <=> :qvec
  LIMIT :dense_limit
),
sparse AS (
  SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS rank
  FROM chunks c JOIN documents d ON d.id = c.document_id,
       websearch_to_tsquery('english', :query) q
  WHERE c.tsv @@ q AND d.acl_groups && :user_groups AND d.status = 'indexed'{filters}
  ORDER BY ts_rank_cd(c.tsv, q) DESC
  LIMIT :sparse_limit
),
fused AS (
  SELECT id, SUM(1.0 / (:rrf_k + rank)) AS rrf
  FROM (SELECT * FROM dense UNION ALL SELECT * FROM sparse) u
  GROUP BY id
  ORDER BY rrf DESC
  LIMIT :fusion_limit
)
SELECT c.id, c.document_id, c.text, c.locator, c.heading_path, c.ordinal,
       d.uri, d.title, f.rrf
FROM fused f
JOIN chunks c ON c.id = f.id
JOIN documents d ON d.id = c.document_id
ORDER BY f.rrf DESC
"""


class HybridRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def retrieve(
        self,
        query: str,
        user_groups: frozenset[str],
        filters: RetrievalFilters | None = None,
        limit: int | None = None,
    ) -> list[Chunk]:
        if not query.strip():
            return []

        qvec = await embed_query(query)
        return await self.retrieve_with_vector(qvec, query, user_groups, filters, limit)

    async def retrieve_with_vector(
        self,
        qvec: list[float],
        query: str,
        user_groups: frozenset[str],
        filters: RetrievalFilters | None = None,
        limit: int | None = None,
    ) -> list[Chunk]:
        filter_sql, filter_params = build_filter_sql(filters)
        stmt = sql_text(HYBRID_SQL.format(filters=filter_sql))

        params: dict[str, Any] = {
            "qvec": str(qvec),
            "query": sanitize_tsquery(query),
            "user_groups": list(user_groups),
            "dense_limit": settings.dense_candidates,
            "sparse_limit": settings.sparse_candidates,
            "rrf_k": settings.rrf_k,
            "fusion_limit": limit or settings.fusion_limit,
            **filter_params,
        }

        await self._session.execute(sql_text(f"SET LOCAL hnsw.ef_search = {settings.hnsw_ef_search}"))
        rows = (await self._session.execute(stmt, params)).mappings().all()

        chunks = [
            Chunk(
                id=row["id"],
                document_id=row["document_id"],
                text=row["text"],
                locator=row["locator"] or {},
                heading_path=list(row["heading_path"] or []),
                ordinal=row["ordinal"],
                uri=row["uri"],
                document_title=row["title"],
                score=float(row["rrf"]),
            )
            for row in rows
        ]
        retrieval_candidates.observe(len(chunks))
        log.info(
            "retrieved",
            candidates=len(chunks),
            chunk_ids=[str(c.id) for c in chunks[:10]],
            groups=len(user_groups),
        )
        return chunks


def dedupe_by_id(chunk_lists: list[list[Chunk]]) -> list[Chunk]:
    """Union sub-query results, keeping the best score per chunk."""
    best: dict[uuid.UUID, Chunk] = {}
    for chunks in chunk_lists:
        for c in chunks:
            existing = best.get(c.id)
            if existing is None or c.score > existing.score:
                best[c.id] = c
    return sorted(best.values(), key=lambda c: c.score, reverse=True)
