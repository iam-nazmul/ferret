"""websearch_to_tsquery raises on some punctuation — sanitize, don't swallow."""

from app.retrieval.query import sanitize_tsquery


def test_strips_operators_that_break_tsquery():
    for ch in "<>()[]{}!&|:*\\\"'":
        assert ch not in sanitize_tsquery(f"refund {ch} policy")


def test_preserves_meaningful_terms():
    out = sanitize_tsquery("What is the SOC 2 Type II refund window?")
    assert "SOC" in out and "refund" in out and "window" in out


def test_hyphens_become_spaces():
    assert sanitize_tsquery("multi-tenant") == "multi tenant"


def test_collapses_whitespace_and_bounds_length():
    assert sanitize_tsquery("a    b") == "a b"
    assert len(sanitize_tsquery("x " * 5000)) <= 1000


def test_empty_input_is_safe():
    assert sanitize_tsquery("") == ""
