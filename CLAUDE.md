# CLAUDE.md — Ferret

Working instructions for developers and coding agents. **[SPEC.md](SPEC.md) is the source of truth for *what* we build; this file is *how* you work in the repo.** When the two disagree, SPEC.md wins — and fix this file.

Read the README.md in a module's directory before editing that module.

---

## Architecture

### Module map (what depends on what)

```
                          ┌───────────────────────────────┐
                          │  ui/  — Streamlit             │
                          │  chat · sources · memory ·    │
                          │  admin                        │
                          └───────────────┬───────────────┘
                                          │ HTTP + SSE
                                          │ (no DB access, no LLM calls)
                          ┌───────────────▼───────────────┐
                          │  app/api/  — FastAPI          │
                          │  routes · SSE · OIDC authn ·  │
                          │  user_groups extraction       │
                          └───────────────┬───────────────┘
                                          │ invokes the graph
                          ┌───────────────▼───────────────┐
                          │  app/graph/  — LangGraph      │
                          │  route → decompose →          │
                          │  retrieve → rerank → grade →  │
                          │  generate → verify            │
                          └──┬─────────────┬────────────┬─┘
                             │             │            │
          ┌──────────────────▼──┐  ┌───────▼───────┐  ┌─▼──────────────┐
          │ app/retrieval/      │  │ app/memory/   │  │ app/llm/       │
          │ hybrid SQL · RRF ·  │  │ checkpointer  │  │ Anthropic      │
          │ reranker client     │  │ · store ·     │  │ client ·       │
          │                     │  │ extraction    │  │ prompts ·      │
          │                     │  │               │  │ cache layout   │
          └──────────┬──────────┘  └───────┬───────┘  └─┬──────────────┘
                     │                     │            │
                     └──────────┬──────────┘            │ HTTPS
                                │                       │
                     ┌──────────▼──────────┐   ┌────────▼─────────┐
                     │ app/models/         │   │  Claude API      │
                     │ SQLAlchemy ·        │   │  claude-opus-5   │
                     │ Alembic migrations  │   │  claude-haiku-4-5│
                     └──────────▲──────────┘   └──────────────────┘
                                │
                     ┌──────────┴──────────┐
                     │ app/ingest/         │       ┌──────────────┐
                     │ discover · fetch ·  │       │ eval/        │
                     │ parse · chunk ·     │       │ datasets ·   │
                     │ embed · upsert      │       │ evaluators · │
                     │ (Celery workers)    │       │ CI gate      │
                     └─────────────────────┘       └──────┬───────┘
                                                          │ calls the graph
                                                          │ like a client
                                                          ▼
                                                    app/graph/
```

**Dependency rule — enforced in review:** arrows point one way only.
`ui → api → graph → {retrieval, memory, llm} → models`. `ingest` writes through `models` and never imports `graph`. `eval` imports `graph` as a black box and nothing below it. **A module must never import from a module above it.** If you need the reverse, you need an argument passed down, not an import.

### Request lifecycle (follow this when debugging)

| # | Where | What happens | Fails how |
|---|---|---|---|
| 1 | `app/api/routes/chat.py` | JWT verified, `user_groups` extracted from the group claim | 401 / 403 |
| 2 | `app/graph/nodes/route.py` | simple vs. multi-hop classification | falls back to simple |
| 3 | `app/graph/nodes/retrieve.py` → `app/retrieval/hybrid.py` | one SQL round trip, dense + sparse + RRF, **ACL in the WHERE** | empty candidate list |
| 4 | `app/graph/nodes/rerank.py` → `app/retrieval/reranker.py` | 30 → top 8 | reranker down → fall back to RRF order, log it |
| 5 | `app/graph/nodes/grade.py` | Haiku binary sufficiency grade | "no" → 1 retry with a rewritten query, then give up |
| 6 | `app/graph/nodes/generate.py` → `app/llm/client.py` | Opus 5, chunks as `document` blocks with `citations.enabled` | `stop_reason == "refusal"` → surface it |
| 7 | `app/graph/nodes/verify.py` | every factual sentence carries a citation | sets `groundedness_violation`, does not block |
| 8 | `app/api/sse.py` | `status` → `sources` → `token`* → `citation` → `done` | `error` event, never a silent hang |

Every step emits a LangSmith span. **If you can't explain a bad answer from the trace, the trace is missing data — fix the instrumentation, not just the bug.**

---

## Hard rules

These are correctness and safety invariants. Breaking one is a blocking review comment, not a preference.

1. **ACL goes in the innermost `WHERE`.** Never filter retrieved chunks in Python after the query. Unauthorized text must never reach a prompt. See `app/retrieval/README.md`.
2. **Never construct a prompt outside `app/llm/`.** Prompts live in `app/llm/prompts/` as named constants. A prompt string inline in a node is a review reject — it breaks cache stability and makes eval unable to diff prompt changes.
3. **Model IDs are `claude-opus-5` and `claude-haiku-4-5`**, referenced through `app/llm/models.py` constants — never as string literals at call sites, never with a date suffix appended.
4. **`thinking={"type": "adaptive"}`.** `budget_tokens` returns 400 on Opus 5. No assistant prefill — it also returns 400.
5. **Citations come from the API, not the model.** Chunks are passed as separate `document` blocks with `citations: {"enabled": True}`. Never ask the model to write citation markers itself, and never post-process them into existence.
6. **Ingestion is idempotent on `(source_id, uri, content_hash)`.** Any new ingest path must be safe to re-run.
7. **Chunk upserts are transactional** — delete + reinsert by `document_id` in one transaction. A partial upsert leaves the index lying.
8. **No secrets in code.** Config comes from env via `app/config.py`.
9. **Never log document text at INFO.** Chunk IDs and scores, yes; content, no — the logs have a different retention class than the corpus.
10. **Ship a migration with every model change.** `app/models/` changes without an Alembic revision break deploys.

---

## Setup

```bash
cp .env.example .env          # fill ANTHROPIC_API_KEY, OPENAI_API_KEY, LANGSMITH_API_KEY, DATABASE_URL
uv sync                       # or: pip install -e ".[dev]"
docker compose -f deploy/compose.yml up -d postgres redis reranker
alembic upgrade head
```

Run it:

```bash
uvicorn app.api.main:app --reload --port 8000    # API
celery -A app.ingest.worker worker -l info       # ingestion workers
celery -A app.ingest.worker beat -l info         # scheduler
streamlit run ui/app.py                          # UI on :8501
```

## Common commands

| Task | Command |
|---|---|
| Unit tests | `pytest tests/unit -q` |
| Integration (spins up Postgres) | `pytest tests/integration -q` |
| Lint + format | `ruff check --fix . && ruff format .` |
| Types | `mypy app/` |
| New migration | `alembic revision --autogenerate -m "add x"` |
| Ingest one source now | `python -m app.ingest.cli run --source-id <uuid>` |
| Reindex everything | `python -m app.ingest.cli reindex --all` |
| Eval, one dataset | `python -m eval.run_eval --dataset ferret-golden-qa` |
| Eval, full CI gate | `python -m eval.run_eval --gate` |
| Ask a question from the CLI | `python -m app.graph.cli "your question" --user-groups eng,all` |

---

## Recipes

**Adding a new source type** (e.g. SharePoint): implement a discoverer in `app/ingest/discover/`, a fetcher in `app/ingest/fetch/`, register the `kind` string in `app/ingest/registry.py`, add a parser in `app/ingest/parse/` if the format is new. Chunking, embedding, and upsert are shared — do not fork them. Details in `app/ingest/README.md`.

**Changing retrieval** (k values, fusion, a new signal): change it behind the `Retriever` protocol in `app/retrieval/base.py`, then **run `python -m eval.run_eval --gate` before opening the PR**. Retrieval changes without eval numbers in the PR description get sent back.

**Changing a prompt**: edit the constant in `app/llm/prompts/`, then run the gate. Prompt edits are the highest-variance change in the repo and the cheapest to regress silently.

**Adding an evaluator**: `eval/evaluators.py`, follow the LangSmith signature (`inputs`, `outputs`, `reference_outputs`). Prefer a deterministic evaluator over an LLM judge whenever the property is checkable in code — it's free, fast, and not arguable.

**Adding an API endpoint**: route in `app/api/routes/`, Pydantic schema in `app/api/schemas.py`, and it must take `user_groups` from the authenticated principal — never from the request body.

---

## Definition of done

A change is not done until:

- `pytest`, `ruff`, and `mypy` pass.
- If it touched retrieval, prompts, or the graph: `python -m eval.run_eval --gate` passes, and **the numbers are in the PR description**.
- If it touched `app/models/`: a migration exists and `alembic upgrade head && alembic downgrade -1` both work.
- If it touched ACL, auth, or retrieval filtering: `pytest tests/integration/test_acl.py` passes.
- The module README is updated if you changed a contract, an invariant, or a file layout.

## Pitfalls we have already hit

- **`cache_read_input_tokens` silently going to zero.** Something volatile (a timestamp, an unsorted dict, a per-request tool list) drifted into the cached prefix. Check `ferret_cache_read_tokens` after any change to `app/llm/`.
- **Reranker latency spikes** under cold start. It is a separate service; the client has a timeout and an RRF-order fallback. Don't remove the fallback.
- **`websearch_to_tsquery` throws on some punctuation.** Sanitize in `app/retrieval/hybrid.py`, don't wrap the whole query in try/except and return empty.
- **LangGraph checkpointer growth.** Threads accumulate; the retention job in `app/memory/retention.py` is not optional in prod.
- **Streamlit reruns the whole script on every interaction.** Anything expensive belongs behind `@st.cache_resource`, and no LLM call belongs in `ui/` at all.
