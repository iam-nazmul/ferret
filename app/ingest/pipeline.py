"""The per-document stage sequence."""

import hashlib
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.chunk import chunk_document
from app.ingest.embed import embed_texts
from app.ingest.parse import parse_content
from app.ingest.registry import get_handlers
from app.ingest.types import Discovered
from app.ingest.upsert import mark_failed, upsert_document
from app.logging import get_logger
from app.metrics import ingest_docs
from app.models import Document, Source

log = get_logger(__name__)


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def ingest_source(session: AsyncSession, source_id: uuid.UUID) -> dict[str, int]:
    source = (
        await session.execute(select(Source).where(Source.id == source_id))
    ).scalar_one_or_none()
    if source is None or not source.enabled:
        return {"discovered": 0, "indexed": 0, "skipped": 0, "failed": 0}

    discoverer, _ = get_handlers(source.kind)
    discovered = await discoverer(source.uri, source.crawl_config or {})
    log.info("discovered", source_id=str(source_id), count=len(discovered))

    stats = {"discovered": len(discovered), "indexed": 0, "skipped": 0, "failed": 0}
    for item in discovered:
        outcome = await ingest_document(session, source, item)
        stats[outcome] += 1

    from datetime import UTC, datetime

    source.last_run_at = datetime.now(UTC)
    await session.commit()
    return stats


async def ingest_document(session: AsyncSession, source: Source, item: Discovered) -> str:
    """Returns 'indexed' | 'skipped' | 'failed'."""
    # Read into locals: rollback expires ORM attributes, and touching one in the
    # except handler raises MissingGreenlet.
    source_id = source.id
    source_kind = source.kind
    default_acl = list(source.acl_groups)
    _, fetcher = get_handlers(source_kind)

    existing = (
        await session.execute(
            select(Document).where(Document.source_id == source_id, Document.uri == item.uri)
        )
    ).scalar_one_or_none()
    prior_etag = (existing.doc_metadata or {}).get("etag") if existing else None

    try:
        fetched = await fetcher(item.uri, prior_etag)
        if fetched.unchanged:
            ingest_docs.labels(status="skipped").inc()
            return "skipped"

        digest = content_hash(fetched.content)
        if existing is not None and existing.content_hash == digest:
            ingest_docs.labels(status="skipped").inc()
            return "skipped"

        parsed = parse_content(fetched)
        chunks = chunk_document(parsed)
        if not chunks:
            raise ValueError("parser produced no chunks")

        embeddings = await embed_texts([c.text for c in chunks])

        metadata: dict[str, Any] = dict(item.metadata)
        if fetched.etag:
            metadata["etag"] = fetched.etag

        await upsert_document(
            session,
            source_id=source_id,
            uri=item.uri,
            title=parsed.title,
            content_hash=digest,
            acl_groups=item.acl_groups or default_acl,
            metadata=metadata,
            page_count=parsed.page_count,
            chunks=chunks,
            embeddings=embeddings,
        )
        ingest_docs.labels(status="indexed").inc()
        return "indexed"

    except Exception as exc:
        await session.rollback()
        await mark_failed(session, source_id, item.uri, f"{type(exc).__name__}: {exc}")
        ingest_docs.labels(status="failed").inc()
        return "failed"
