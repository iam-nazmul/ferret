"""Context packing: chunks -> document blocks with citations enabled."""

import json

from app.llm.documents import pack_context, to_document_block
from tests.conftest import make_chunk


def test_each_chunk_becomes_its_own_document_block():
    chunks = [make_chunk(), make_chunk()]
    content = pack_context(chunks, "question?")
    docs = [c for c in content if c["type"] == "document"]
    assert len(docs) == 2


def test_citations_are_enabled_on_every_block():
    """All or none — a mixed request is rejected by the API."""
    content = pack_context([make_chunk(), make_chunk()], "q")
    docs = [c for c in content if c["type"] == "document"]
    assert all(d["citations"] == {"enabled": True} for d in docs)


def test_locator_travels_in_context_for_deep_linking():
    block = to_document_block(make_chunk(page=42))
    assert json.loads(block["context"])["locator"]["page"] == 42


def test_title_includes_heading_path():
    block = to_document_block(make_chunk(title="Refund Policy", heading_path=["Billing", "Refunds"]))
    assert "Refund Policy" in block["title"]
    assert "Billing > Refunds" in block["title"]


def test_question_comes_after_the_documents():
    content = pack_context([make_chunk()], "What is the refund window?")
    assert content[-1]["type"] == "text"
    assert "What is the refund window?" in content[-1]["text"]


def test_memories_are_placed_before_the_question():
    content = pack_context([make_chunk()], "q", memories="User works on billing")
    assert "User works on billing" in content[-1]["text"]


def test_empty_chunk_list_still_produces_the_question():
    content = pack_context([], "q")
    assert len(content) == 1 and content[0]["type"] == "text"
