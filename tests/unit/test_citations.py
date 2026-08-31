"""Citation mapping: API output -> our Citation type. Never parsed out of prose."""

from app.llm.citations import answer_text, deep_link, extract_citations
from tests.conftest import make_chunk


def test_maps_document_index_to_chunk():
    chunks = [make_chunk(uri="s3://a.pdf"), make_chunk(uri="s3://b.pdf")]
    blocks = [
        {"type": "text", "text": "Answer.", "citations": [{"document_index": 1, "cited_text": "30 days"}]}
    ]
    citations = extract_citations(blocks, chunks)
    assert len(citations) == 1
    assert citations[0].uri == "s3://b.pdf"
    assert citations[0].cited_text == "30 days"


def test_out_of_range_index_is_dropped_not_crashed():
    chunks = [make_chunk()]
    blocks = [{"type": "text", "citations": [{"document_index": 99, "cited_text": "x"}]}]
    assert extract_citations(blocks, chunks) == []


def test_blocks_without_citations_yield_none():
    assert extract_citations([{"type": "text", "text": "Hi."}], [make_chunk()]) == []


def test_answer_text_concatenates_text_blocks_only():
    blocks = [
        {"type": "text", "text": "Part one. "},
        {"type": "thinking", "text": "hidden"},
        {"type": "text", "text": "Part two."},
    ]
    assert answer_text(blocks) == "Part one. Part two."


def test_deep_link_uses_page_for_pdfs():
    c = extract_citations(
        [{"type": "text", "citations": [{"document_index": 0, "cited_text": "x"}]}],
        [make_chunk(page=12)],
    )[0]
    assert deep_link(c).endswith("#page=12")


def test_deep_link_uses_anchor_for_web():
    chunk = make_chunk(uri="https://wiki/sla")
    chunk.locator = {"anchor": "#uptime"}
    c = extract_citations(
        [{"type": "text", "citations": [{"document_index": 0, "cited_text": "x"}]}], [chunk]
    )[0]
    assert deep_link(c) == "https://wiki/sla#uptime"


def test_deep_link_falls_back_to_uri():
    chunk = make_chunk(uri="https://wiki/page")
    chunk.locator = {}
    c = extract_citations(
        [{"type": "text", "citations": [{"document_index": 0, "cited_text": "x"}]}], [chunk]
    )[0]
    assert deep_link(c) == "https://wiki/page"
