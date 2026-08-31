"""Ingestion idempotency at the hashing level."""

from app.ingest.pipeline import content_hash
from app.ingest.registry import REGISTRY, get_handlers


def test_content_hash_is_stable_and_distinguishing():
    assert content_hash(b"abc") == content_hash(b"abc")
    assert content_hash(b"abc") != content_hash(b"abd")


def test_every_registered_kind_has_both_handlers():
    for kind in REGISTRY:
        discoverer, fetcher = get_handlers(kind)
        assert callable(discoverer) and callable(fetcher)


def test_unknown_kind_raises_with_a_useful_message():
    try:
        get_handlers("sharepoint")
    except ValueError as exc:
        assert "sharepoint" in str(exc)
    else:
        raise AssertionError("expected ValueError")
