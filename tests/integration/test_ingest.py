"""Ingestion idempotency: run twice, assert no duplicate chunks."""


import pytest
from sqlalchemy import func, select

from app.ingest.types import Discovered, Fetched
from app.models import Chunk, Document, DocumentStatus
from tests.fixtures.corpus import fake_embedding, seed_source

HTML = b"<html><head><title>Refund Policy</title></head><body><h1>Refunds</h1><p>The refund window is 30 days from the invoice date.</p></body></html>"


async def _ingest_once(session, source, monkeypatch, content: bytes = HTML, etag: str = "v1"):
    """Drive the pipeline with fake fetch/embed so no network is touched."""
    from app.ingest import pipeline

    async def fake_fetch(uri, prior_etag=None):
        if prior_etag == etag:
            return Fetched(uri=uri, content=b"", content_type="", etag=etag, unchanged=True)
        return Fetched(uri=uri, content=content, content_type="text/html", etag=etag)

    async def fake_embed(texts):
        return [fake_embedding(t) for t in texts]

    def fake_handlers(kind):
        async def discover(uri, config):
            return [Discovered(uri="https://example.test/refunds")]

        return discover, fake_fetch

    monkeypatch.setattr(pipeline, "get_handlers", fake_handlers)
    monkeypatch.setattr(pipeline, "embed_texts", fake_embed)
    return await pipeline.ingest_source(session, source.id)


async def test_first_run_indexes(clean_session, monkeypatch):
    source = await seed_source(clean_session, ["all"])
    await clean_session.commit()

    stats = await _ingest_once(clean_session, source, monkeypatch)
    assert stats["indexed"] == 1

    count = await clean_session.scalar(select(func.count()).select_from(Chunk))
    assert count >= 1


async def test_second_run_is_a_no_op(clean_session, monkeypatch):
    """The property that makes every stage safe to re-run."""
    source = await seed_source(clean_session, ["all"])
    await clean_session.commit()

    await _ingest_once(clean_session, source, monkeypatch)
    first = await clean_session.scalar(select(func.count()).select_from(Chunk))

    stats = await _ingest_once(clean_session, source, monkeypatch)
    second = await clean_session.scalar(select(func.count()).select_from(Chunk))

    assert stats["skipped"] == 1
    assert stats["indexed"] == 0
    assert first == second, "re-running duplicated chunks"


async def test_changed_content_replaces_chunks_without_duplicating(clean_session, monkeypatch):
    source = await seed_source(clean_session, ["all"])
    await clean_session.commit()

    await _ingest_once(clean_session, source, monkeypatch)
    changed = HTML.replace(b"30 days", b"45 days")
    stats = await _ingest_once(clean_session, source, monkeypatch, content=changed, etag="v2")

    assert stats["indexed"] == 1
    texts = (await clean_session.execute(select(Chunk.text))).scalars().all()
    assert any("45 days" in t for t in texts)
    assert not any("30 days" in t for t in texts), "stale chunks were left behind"


async def test_parse_failure_marks_document_failed(clean_session, monkeypatch):
    source = await seed_source(clean_session, ["all"])
    await clean_session.commit()

    stats = await _ingest_once(clean_session, source, monkeypatch, content=b"", etag="v9")
    assert stats["failed"] == 1

    doc = (await clean_session.execute(select(Document))).scalars().first()
    assert doc.status == DocumentStatus.FAILED.value
    assert doc.error


async def test_upsert_is_transactional(clean_session):
    """A partial upsert would leave the index lying about the corpus."""
    from app.ingest.types import PreparedChunk
    from app.ingest.upsert import upsert_document

    source = await seed_source(clean_session, ["all"])
    await clean_session.commit()

    chunks = [
        PreparedChunk(text=f"Chunk {i}", locator={"page": i}, heading_path=[], token_count=3, ordinal=i)
        for i in range(3)
    ]
    with pytest.raises(ValueError):
        await upsert_document(
            clean_session,
            source_id=source.id,
            uri="https://example.test/x",
            title="X",
            content_hash="abc",
            acl_groups=["all"],
            metadata={},
            page_count=1,
            chunks=chunks,
            embeddings=[fake_embedding("a")],  # length mismatch -> strict zip raises
        )
