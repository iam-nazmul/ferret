"""Seeded corpus factory.

One place to change when the schema moves, rather than hand-built rows per test.
Embeddings are deterministic and locally generated — no test hits an embedding API.
"""

import hashlib
import math
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Chunk, Document, DocumentStatus, Source, SourceKind


def fake_embedding(text: str, dims: int | None = None) -> list[float]:
    """Deterministic unit vector from a hash. Similar text does NOT give similar vectors —
    integration tests assert on ACL and SQL mechanics, not semantic ranking."""
    d = dims or settings.embedding_dims
    digest = hashlib.sha256(text.encode()).digest()
    raw = [(digest[i % len(digest)] - 128) / 128 for i in range(d)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


async def seed_source(
    session: AsyncSession, acl_groups: list[str], kind: str = SourceKind.WEB_SITEMAP.value
) -> Source:
    source = Source(
        id=uuid.uuid4(),
        kind=kind,
        uri=f"https://example.test/{uuid.uuid4().hex[:8]}",
        acl_groups=acl_groups,
        crawl_config={},
    )
    session.add(source)
    await session.flush()
    return source


async def seed_document(
    session: AsyncSession,
    source: Source,
    *,
    title: str,
    texts: list[str],
    acl_groups: list[str] | None = None,
    doc_type: str = "policy",
    effective_date: str | None = None,
    status: str = DocumentStatus.INDEXED.value,
) -> Document:
    metadata: dict = {"doc_type": doc_type}
    if effective_date:
        metadata["effective_date"] = effective_date

    doc = Document(
        id=uuid.uuid4(),
        source_id=source.id,
        uri=f"https://example.test/{title.lower().replace(' ', '-')}",
        title=title,
        content_hash=hashlib.sha256(("".join(texts)).encode()).hexdigest(),
        acl_groups=acl_groups or list(source.acl_groups),
        doc_metadata=metadata,
        status=status,
        page_count=len(texts),
    )
    session.add(doc)
    await session.flush()

    session.add_all(
        [
            Chunk(
                id=uuid.uuid4(),
                document_id=doc.id,
                ordinal=i,
                text=text,
                locator={"page": i + 1},
                heading_path=[title],
                token_count=max(1, len(text) // 4),
                embedding=fake_embedding(text),
            )
            for i, text in enumerate(texts)
        ]
    )
    await session.flush()
    return doc


async def seed_two_tenant_corpus(session: AsyncSession) -> dict:
    """Two documents in two disjoint ACL groups — the shape test_acl.py needs."""
    eng_source = await seed_source(session, ["eng"])
    finance_source = await seed_source(session, ["finance"])

    eng_doc = await seed_document(
        session,
        eng_source,
        title="Deployment Policy",
        texts=[
            "Production deployments require approval from the on-call engineer.",
            "Rollback is performed with the previous container image.",
        ],
        acl_groups=["eng"],
    )
    finance_doc = await seed_document(
        session,
        finance_source,
        title="Refund Policy",
        texts=[
            "The refund window is 30 days from the invoice date.",
            "Enterprise customers may request an extension in writing.",
        ],
        acl_groups=["finance"],
        effective_date="2025-06-01",
    )
    await session.commit()
    return {
        "eng_doc": eng_doc,
        "finance_doc": finance_doc,
        "eng_secret": "on-call engineer",
        "finance_secret": "30 days from the invoice date",
    }
