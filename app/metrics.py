"""Prometheus metrics. Names are referenced by the alerts in SPEC §14."""

from prometheus_client import Counter, Gauge, Histogram

query_latency = Histogram(
    "ferret_query_latency_seconds",
    "End-to-end and per-stage query latency",
    ["stage"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 6, 8, 15),
)
retrieval_candidates = Histogram(
    "ferret_retrieval_candidates", "Candidates after fusion", buckets=(0, 5, 10, 20, 30, 50)
)
cache_read_tokens = Counter(
    "ferret_cache_read_tokens", "Prompt cache read tokens (zero for long = broken prefix)"
)
tokens_total = Counter("ferret_tokens_total", "Tokens consumed", ["kind"])
ingest_docs = Counter("ferret_ingest_docs_total", "Documents processed", ["status"])
groundedness_violations = Counter(
    "ferret_groundedness_violations_total", "Answers with uncited factual sentences"
)
reranker_fallbacks = Counter(
    "ferret_reranker_fallbacks_total", "Times reranking fell back to RRF order"
)
active_requests = Gauge("ferret_active_requests", "In-flight chat requests")
