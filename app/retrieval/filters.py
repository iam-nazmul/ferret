"""Filters -> SQL predicates. Pure functions, unit-tested."""

from typing import Any

from app.retrieval.types import RetrievalFilters


def build_filter_sql(filters: RetrievalFilters | None) -> tuple[str, dict[str, Any]]:
    """Return an SQL fragment (starting with AND, or empty) and its bind parameters."""
    if filters is None or filters.is_empty():
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    if filters.doc_type:
        clauses.append("d.metadata->>'doc_type' = ANY(:doc_type)")
        params["doc_type"] = list(filters.doc_type)

    if filters.effective_after:
        clauses.append("(d.metadata->>'effective_date')::date >= :effective_after")
        params["effective_after"] = filters.effective_after

    if filters.effective_before:
        clauses.append("(d.metadata->>'effective_date')::date <= :effective_before")
        params["effective_before"] = filters.effective_before

    return " AND " + " AND ".join(clauses), params
