# app/retrieval — hybrid search

Dense + sparse retrieval, RRF fusion, reranking. **The ACL boundary is enforced here, in SQL.** Everything this module returns is already authorized for the caller.

Spec: [SPEC.md §8.2–8.4](../../SPEC.md).

## Layout

```
base.py       # Retriever protocol — swap implementations behind this
hybrid.py     # the fused SQL query (dense + sparse + RRF)
reranker.py   # HTTP client for the bge-reranker service, with fallback
embed.py      # query embedding (shared config with app/ingest/embed.py)
filters.py    # doc_type / effective_after → SQL predicates
query.py      # tsquery sanitization (see the gotcha below)
types.py      # Chunk, Citation
```

## The one rule

```sql
WHERE d.acl_groups && :user_groups AND d.status = 'indexed'
```

**This predicate belongs in the innermost query, in both the dense and sparse CTEs.** Never fetch broadly and filter in Python. If unauthorized text is in the result set, it is one refactor away from being in a prompt, and at that point the only thing preventing a leak is the model's good behavior.

`tests/integration/test_acl.py` asserts this end-to-end. It is not optional and it is not slow.

## Parameters (tuned, don't drift casually)

| Parameter | Value | Why |
|---|---|---|
| dense candidates | 50 | recall headroom for the reranker |
| sparse candidates | 50 | exact-term and identifier matches dense misses |
| RRF `k` | 60 | standard; low sensitivity, don't fiddle |
| post-fusion | 30 | as many as the reranker can handle in budget |
| final top-k | 8 | fits the context and latency budget |
| HNSW | `m=16, ef_construction=64` | build time vs. recall |

Changing any of these means re-running `python -m eval.run_eval --gate` and reporting `retrieval_recall@8`.

## Why hybrid

Dense alone misses exact identifiers ("SOC 2 Type II", ticket numbers, clause labels). Sparse alone misses paraphrase. RRF needs no score normalization between the two, which is why it beats a weighted sum here — the scores aren't on comparable scales.

The reranker is what converts recall into precision, and precision is what drives groundedness. Removing it to save 400ms costs more than it saves.

## Reranker fallback

If the reranker service times out or errors, **return the top 8 by RRF order and log a warning with a counter**. Do not raise — a degraded ranking is a usable answer; an exception is an outage. The counter exists so this doesn't silently become the normal path.

## Gotchas

- **`websearch_to_tsquery` raises on some punctuation.** Sanitize the query in `hybrid.py`. Don't wrap the whole search in try/except and return empty — that turns a parsing bug into "Ferret knows nothing."
- **Embedding config must match ingestion exactly** — same model, same 1024d truncation. A mismatch produces silently terrible results, not an error. Both sides read from `app/config.py`; keep it that way.
- **`ef_search` matters at query time**, not just `ef_construction` at build. Set it per session in `hybrid.py`.
- Empty `user_groups` must return zero rows, not all rows. `&&` with an empty array does the right thing — don't "helpfully" skip the predicate when the set is empty.
