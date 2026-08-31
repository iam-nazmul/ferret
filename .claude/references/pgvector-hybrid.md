# Reference — Postgres, pgvector, and the hybrid query

Everything Ferret stores lives in one Postgres: corpus, vectors, BM25, LangGraph checkpointer and store.

## The hybrid query

```sql
WITH dense AS (
  SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> :qvec) AS rank
  FROM chunks c JOIN documents d ON d.id = c.document_id
  WHERE d.acl_groups && :user_groups AND d.status = 'indexed'
  ORDER BY c.embedding <=> :qvec LIMIT 50
),
sparse AS (
  SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, q) DESC) AS rank
  FROM chunks c JOIN documents d ON d.id = c.document_id,
       websearch_to_tsquery('english', :query) q
  WHERE c.tsv @@ q AND d.acl_groups && :user_groups AND d.status = 'indexed'
  ORDER BY ts_rank_cd(c.tsv, q) DESC LIMIT 50
)
SELECT id, SUM(1.0 / (60 + rank)) AS rrf
FROM (SELECT * FROM dense UNION ALL SELECT * FROM sparse) u
GROUP BY id ORDER BY rrf DESC LIMIT 30;
```

**The ACL predicate is in both CTEs, innermost.** Not negotiable — see `.claude/skills/acl-audit`.

**RRF over weighted score fusion** because cosine distance and `ts_rank_cd` are not on comparable scales; rank fusion needs no normalization. `k=60` is the standard value and has low sensitivity.

## Operators and gotchas

| | |
|---|---|
| `<=>` | cosine distance (matches `vector_cosine_ops`) |
| `<->` | L2 — **not** what our index is built for; silently poor results |
| `&&` | array overlap; empty `:user_groups` correctly yields no rows |
| `@@` | tsvector match |

- **`websearch_to_tsquery` raises on some punctuation.** Sanitize the query string. Do not wrap the search in try/except returning empty — that turns a parse bug into "Ferret knows nothing."
- **`ef_search` is a query-time setting**, separate from build-time `ef_construction`. Set it per session or recall quietly underperforms.
- **`vector(1024)` must match the embedding config** in `app/config.py` and in ingestion. Changing dimensions is a full re-index, not a migration.

## Indexes

```sql
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
CREATE INDEX ON chunks USING gin (tsv);
CREATE INDEX ON documents USING gin (acl_groups);
```

`chunks.tsv` is a **generated column** — BM25 can't fall out of sync because there's no way to forget to update it.

On a populated table, build indexes with `CREATE INDEX CONCURRENTLY` in its own non-transactional Alembic revision; a plain `CREATE INDEX` locks `chunks` for the duration.

## Performance

- ~10M chunks (≈200K documents) at p95 < 300ms on 8 vCPU / 32GB. Beyond that: partition on `acl_groups`/`doc_type` first; move only vectors to Qdrant as a last resort, leaving the schema intact.
- Bulk chunk inserts use `execute_values` or `COPY`, never per-row ORM inserts — ingestion throughput is dominated by this.
- Connection pools: `api` (3 × pool) + `worker` (2 × pool) + migrations. Defaults will exhaust a small managed instance.
- `EXPLAIN (ANALYZE, BUFFERS)` on the hybrid query is the first move for any latency regression. A sequential scan on `chunks` means the HNSW index isn't being used — usually an operator or dimension mismatch.

## Migrations

Backward-compatible only in v1: rollback is "previous image + `alembic downgrade -1`", which requires the old code to run against the new schema. Add columns nullable, backfill separately, drop later.

Autogenerate misses index options, generated columns, `vector` type changes, and constraint renames. Read every generated revision before committing.

LangGraph's tables (`checkpoints`, `checkpoint_writes`, `store`) are managed by its own `setup()`, not our migrations.
