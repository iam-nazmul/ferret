"""Chunking is deterministic logic — the cheapest place to catch refactor damage."""

from app.ingest.chunk import chunk_document, count_tokens, heading_prefix
from app.ingest.types import Parsed, ParsedBlock


def _parsed(blocks):
    return Parsed(title="Doc", blocks=blocks)


def test_heading_prefix_is_attached():
    parsed = _parsed(
        [ParsedBlock(text="Data is kept 90 days.", locator={"page": 1}, heading_path=["Security", "Retention"])]
    )
    chunks = chunk_document(parsed)
    assert chunks[0].text.startswith("Security > Retention\n\n")


def test_no_heading_means_no_prefix():
    parsed = _parsed([ParsedBlock(text="Body text here.", locator={"page": 1})])
    assert chunk_document(parsed)[0].text == "Body text here."


def test_chunks_never_merge_across_headings():
    parsed = _parsed(
        [
            ParsedBlock(text="Alpha body.", locator={"page": 1}, heading_path=["A"]),
            ParsedBlock(text="Beta body.", locator={"page": 1}, heading_path=["B"]),
        ]
    )
    chunks = chunk_document(parsed, target_tokens=10_000)
    assert len(chunks) == 2
    assert chunks[0].heading_path == ["A"]
    assert chunks[1].heading_path == ["B"]


def test_oversized_block_is_split_not_dropped():
    long_text = " ".join(f"Sentence number {i} about policy." for i in range(400))
    parsed = _parsed([ParsedBlock(text=long_text, locator={"page": 1})])
    chunks = chunk_document(parsed, target_tokens=100, overlap_tokens=10)
    assert len(chunks) > 1
    assert all(c.token_count <= 250 for c in chunks)


def test_locator_is_preserved():
    parsed = _parsed([ParsedBlock(text="Body.", locator={"page": 7, "bbox": [1, 2, 3, 4]})])
    assert chunk_document(parsed)[0].locator["page"] == 7


def test_ordinals_are_sequential():
    blocks = [
        ParsedBlock(text=f"Paragraph {i} with enough words to matter here.", locator={"page": i})
        for i in range(10)
    ]
    chunks = chunk_document(_parsed(blocks), target_tokens=20, overlap_tokens=0)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_empty_blocks_are_skipped():
    parsed = _parsed([ParsedBlock(text="   ", locator={}), ParsedBlock(text="Real.", locator={})])
    assert len(chunk_document(parsed)) == 1


def test_count_tokens_is_positive():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0 or count_tokens("") == 1


def test_heading_prefix_helper():
    assert heading_prefix([]) == ""
    assert heading_prefix(["A", "B"]) == "A > B\n\n"
