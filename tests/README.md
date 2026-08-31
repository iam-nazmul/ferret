# tests

Unit and integration tests. **Fast by default, real Postgres where it matters.**

```
unit/           # pure logic, no I/O — chunking, RRF, citation mapping, filters
integration/    # testcontainers Postgres + pgvector; the ones that catch real bugs
  test_acl.py           # the security test — see below
  test_ingest.py        # idempotency: run twice, assert no duplicate chunks
  test_retrieval.py     # hybrid SQL against a seeded corpus
  test_migrations.py    # upgrade head → downgrade -1 → upgrade head
fixtures/       # small PDFs, HTML samples, seeded corpus factory
conftest.py     # container lifecycle, session fixtures, fake LLM
```

```bash
pytest tests/unit -q          # seconds, run constantly
pytest tests/integration -q   # ~1 min, spins up Postgres
pytest -q                     # both — required before pushing
```

## test_acl.py

The one test that must never be skipped, marked xfail, or "temporarily" disabled. It seeds documents across two ACL groups, queries as each of two users, and asserts:

1. each user gets only their own documents,
2. the other group's chunk **text does not appear anywhere in the response, the state, or the trace**,
3. a user with empty groups gets zero results, not all results.

A change that breaks this is a data-exposure bug regardless of how it was introduced.

## What to test where

- **Deterministic logic → unit.** Chunk boundaries, RRF math, `locator` → deep link, filter → SQL predicate. These are cheap and catch most refactor damage.
- **Anything with SQL → integration.** The hybrid query is the core of the product and cannot be meaningfully mocked; `&&`, `tsvector`, and HNSW behavior only exist in a real database.
- **Answer quality → not here.** That's `eval/`. Tests assert structure and invariants; eval measures quality. A test that asserts on model output text will be flaky forever.

## Conventions

- **LLM calls are faked in tests** via the `fake_llm` fixture — deterministic canned responses. No test hits the Anthropic API; the suite must run offline and cost nothing.
- The reranker is faked too, but there's one test that exercises the **fallback path** with the service down. That path is load-bearing and otherwise never runs in dev.
- Seeded corpus comes from `fixtures/corpus.py`, not hand-built rows per test. When the schema changes, one file changes.
- Integration tests share one container per session and roll back per test. Don't recreate the container per test unless you enjoy waiting.

## Gotchas

- pgvector needs the extension in the test container image — `pgvector/pgvector:pg16`, not stock `postgres:16`.
- Async tests need `pytest-asyncio` in strict mode; a missing `@pytest.mark.asyncio` silently passes without running anything.
- Testcontainers needs a working Docker socket in CI. If integration tests "pass" suspiciously fast there, check they weren't skipped.
