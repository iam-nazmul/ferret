"""Transactional chunk replacement.

Delete + reinsert by document_id in ONE transaction. A partial upsert leaves the index
lying about the corpus, and nothing downstream can detect it.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.types import PreparedChunk
from app.logging import get_logger
from app.models import Chunk, Document, DocumentStatus

log = get_logger(__name__)


async def upsert_document(
    session: AsyncSession,
    *,
    source_id: uuid.UUID,
    uri: str,
    title: str | None,
    content_hash: str,
    acl_groups: list[str],
    metadata: dict,
    page_count: int | None,
    chunks: list[PreparedChunk],
    embeddings: list[list[float]],
) -> uuid.UUID:
    existing = (
        await session.execute(
            select(Document).where(Document.source_id == source_id, Document.uri == uri)
        )
    ).scalar_one_or_none()

    if existing is None:
        doc = Document(
            id=uuid.uuid4(),
            source_id=source_id,
            uri=uri,
            title=title,
            content_hash=content_hash,
            acl_groups=acl_groups,
            doc_metadata=metadata,
            page_count=page_count,
            status=DocumentStatus.PENDING,
        )
        session.add(doc)
        await session.flush()
    else:
        doc = existing
        doc.title = title
        doc.content_hash = content_hash
        doc.acl_groups = acl_groups
        doc.doc_metadata = metadata
        doc.page_count = page_count
        doc.error = None
        await session.execute(delete(Chunk).where(Chunk.document_id == doc.id))

    session.add_all(
        [
            Chunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                ordinal=c.ordinal,
                text=c.text,
                locator=c.locator,
                heading_path=c.heading_path,
                token_count=c.token_count,
                embedding=vec,
            )
            for c, vec in zip(chunks, embeddings, strict=True)
        ]
    )

    doc.status = DocumentStatus.INDEXED
    doc.indexed_at = datetime.now(UTC)
    await session.commit()

    log.info("upserted", uri=uri, chunks=len(chunks))
    return doc.id


async def mark_failed(session: AsyncSession, source_id: uuid.UUID, uri: str, error: str) -> None:
    doc = (
        await session.execute(
            select(Document).where(Document.source_id == source_id, Document.uri == uri)
        )
    ).scalar_one_or_none()
    if doc is None:
        doc = Document(
            id=uuid.uuid4(),
            source_id=source_id,
            uri=uri,
            content_hash="",
            acl_groups=[],
            status=DocumentStatus.FAILED,
        )
        session.add(doc)
    doc.status = DocumentStatus.FAILED
    doc.error = error[:2000]
    await session.commit()
    log.warning("document_failed", uri=uri, error=error[:200])
