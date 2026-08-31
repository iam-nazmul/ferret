"""The hybrid query against a real database. This cannot be meaningfully mocked."""


from app.retrieval.hybrid import HybridRetriever, dedupe_by_id
from app.retrieval.types import RetrievalFilters
from tests.fixtures.corpus import fake_embedding, seed_document, seed_source


async def _retrieve(session, query, groups=None, filters=None):
    groups = groups or {"all"}
    return await HybridRetriever(session).retrieve_with_vector(
        fake_embedding(query), query, frozenset(groups), filters
    )


async def test_sparse_side_finds_exact_identifiers(clean_session):
    """Dense retrieval misses exact tokens; this is why the query is hybrid."""
    source = await seed_source(clean_session, ["all"])
    await seed_document(
        clean_session,
        source,
        title="Compliance",
        texts=["We maintain SOC 2 Type II certification renewed annually."],
    )
    await clean_session.commit()

    results = await _retrieve(clean_session, "SOC 2 Type II certification")
    assert any("SOC 2" in c.text for c in results)


async def test_punctuation_heavy_query_does_not_crash(clean_session):
    """websearch_to_tsquery raises on some punctuation — sanitization must absorb it."""
    source = await seed_source(clean_session, ["all"])
    await seed_document(clean_session, source, title="Policy", texts=["Refunds within 30 days."])
    await clean_session.commit()

    results = await _retrieve(clean_session, "refund (window) & policy!! <script>")
    assert isinstance(results, list)


async def test_doc_type_filter_excludes_other_types(clean_session):
    source = await seed_source(clean_session, ["all"])
    await seed_document(
        clean_session, source, title="A Policy", texts=["Refund window is 30 days."], doc_type="policy"
    )
    await seed_document(
        clean_session, source, title="A Report", texts=["Refund window is 30 days."], doc_type="report"
    )
    await clean_session.commit()

    results = await _retrieve(
        clean_session, "refund window", filters=RetrievalFilters(doc_type=["policy"])
    )
    assert results
    assert all(c.document_title == "A Policy" for c in results)


async def test_effective_after_filter(clean_session):
    from datetime import date

    source = await seed_source(clean_session, ["all"])
    await seed_document(
        clean_session, source, title="Old", texts=["Refund window is 14 days."],
        effective_date="2024-01-01",
    )
    await seed_document(
        clean_session, source, title="New", texts=["Refund window is 30 days."],
        effective_date="2026-01-01",
    )
    await clean_session.commit()

    results = await _retrieve(
        clean_session,
        "refund window",
        filters=RetrievalFilters(effective_after=date(2025, 1, 1)),
    )
    assert results
    assert all(c.document_title == "New" for c in results)


async def test_empty_query_returns_nothing(clean_session):
    assert await HybridRetriever(clean_session).retrieve("   ", frozenset({"all"})) == []


async def test_results_carry_locators_for_citations(clean_session):
    source = await seed_source(clean_session, ["all"])
    await seed_document(clean_session, source, title="Doc", texts=["Refund window is 30 days."])
    await clean_session.commit()

    results = await _retrieve(clean_session, "refund window")
    assert results
    assert "page" in results[0].locator


def test_dedupe_keeps_the_best_score():
    from tests.conftest import make_chunk

    chunk = make_chunk(score=0.5)
    duplicate = make_chunk(score=0.9)
    duplicate.id = chunk.id

    merged = dedupe_by_id([[chunk], [duplicate]])
    assert len(merged) == 1
    assert merged[0].score == 0.9
