"""Filters -> SQL predicates."""

from datetime import date

from app.retrieval.filters import build_filter_sql
from app.retrieval.types import RetrievalFilters


def test_empty_filters_produce_no_sql():
    assert build_filter_sql(None) == ("", {})
    assert build_filter_sql(RetrievalFilters()) == ("", {})


def test_doc_type_filter():
    sql, params = build_filter_sql(RetrievalFilters(doc_type=["policy", "contract"]))
    assert sql.startswith(" AND ")
    assert "doc_type" in sql
    assert params["doc_type"] == ["policy", "contract"]


def test_date_filters_combine():
    sql, params = build_filter_sql(
        RetrievalFilters(effective_after=date(2025, 1, 1), effective_before=date(2026, 1, 1))
    )
    assert sql.count("AND") == 2
    assert params["effective_after"] == date(2025, 1, 1)
    assert params["effective_before"] == date(2026, 1, 1)


def test_filters_are_parameterized_not_interpolated():
    """No user value may appear inline in the SQL string."""
    sql, params = build_filter_sql(RetrievalFilters(doc_type=["'; DROP TABLE chunks; --"]))
    assert "DROP TABLE" not in sql
    assert params["doc_type"] == ["'; DROP TABLE chunks; --"]
