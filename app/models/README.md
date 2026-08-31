# app/models — schema and migrations

SQLAlchemy models plus Alembic migrations. **One Postgres holds everything**: corpus, vectors, BM25 index, LangGraph checkpointer, LangGraph store.

Spec: [SPEC.md §6](../../SPEC.md).

## Layout

```
base.py         # declarative base, session factory, engine config
source.py       # sources
document.py     # documents
chunk.py        # chunks (embedding + tsv)
feedback.py     # feedback
migrations/     # Alembic revisions
```

LangGraph's own tables (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `store`) are created in the **public schema by LangGraph's own `setup()`**, which runs at API startup — not by our migrations. Don't hand-write revisions for them. They carry no `created_at`: the timestamp lives inside `checkpoint->>'ts'`, which is what `app/memory/retention.py` expires on.

## Key schema decisions

- **`documents.acl_groups text[]` with a GIN index.** Retrieval filters with `&&` against the user's groups. Denormalized onto documents (not joined from a permissions table) because it has to be cheap enough to sit in the innermost WHERE of every query.
- **`chunks.tsv` is a generated column.** BM25 stays in sync automatically; there is no way to forget to update it.
- **`chunks.locator jsonb`** — `{page, bbox}` for PDFs, `{anchor, char_start}` for web. Deliberately untyped because it varies by source type; the UI branches on shape.
- **`documents.content_hash`** drives ingestion idempotency (§7).
- **HNSW** `m=16, ef_construction=64` on `embedding vector_cosine_ops`.

## Migrations

```bash
alembic revision --autogenerate -m "add x"
alembic upgrade head
alembic downgrade -1        # must work — deploys roll back with this
```

**Every model change ships with a migration in the same PR.** Rules:

- **Backward-compatible only in v1.** The rollback path is "previous image + `downgrade -1`", which only works if the old code runs against the new schema. Add columns nullable, backfill separately, drop in a later release.
- **Autogenerate misses things** — index options, generated columns, `vector` type changes, constraint renames. Read every generated revision before committing.
- **Never edit a migration that has run anywhere.** Write a new one.
- Index creation on `chunks` locks the table. Use `CREATE INDEX CONCURRENTLY` in a separate non-transactional revision for anything on a populated table.

## Gotchas

- `vector(1024)` must match the embedding config in `app/config.py`. Changing dimensions is a full re-index, not a migration — plan it as a project.
- `ON DELETE CASCADE` from sources → documents → chunks means deleting a source is instant and irreversible.
- The session factory is async (`AsyncSession`). Don't mix in a sync engine for "just a quick script" — connection pool exhaustion under load is the result.
- Bulk chunk inserts should use `execute_values`/`copy`, not per-row ORM inserts. Ingestion throughput is dominated by this.
