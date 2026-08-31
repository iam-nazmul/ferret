# Ferret — Enterprise Document Assistant

**Status:** Draft v1 · **Date:** 2026-08-31 · **Owner:** nazmul@glascutr.com

---

## 1. Overview

Ferret is an enterprise document assistant. It indexes an organization's scattered knowledge — hundreds of PDFs (policies, contracts, manuals, reports) plus internal and external web sources — and answers questions in a chat interface **with citations**.

Four pillars:

| Pillar | What it delivers |
|---|---|
| **RAG** | Hybrid retrieval (dense + BM25) → rerank → grounded answer with inline citations |
| **Memory** | Thread-level short-term (conversation) + user-level long-term (role, preferences, active projects) |
| **LangSmith eval** | Golden dataset, offline evaluator suite, CI regression gate, production feedback loop |
| **UI** | Simple chat UI — sources panel, citation highlighting, feedback buttons, admin ingestion view |

**Definition of success, in one line:** groundedness ≥ 0.95 and correctness ≥ 0.85 on the golden set, p95 latency ≤ 6s, and a clickable source next to every factual claim.

---

## 2. Goals and Non-Goals

### 2.1 Goals (G)

- **G1** — Ingest from multiple heterogeneous sources (PDF, HTML, Confluence/Notion exports, sitemap-driven crawl) with incremental re-indexing.
- **G2** — A verifiable citation on every answer; no claim without a source ("I don't know" is the correct behavior).
- **G3** — Per-user, per-document **ACL** — enforced at retrieval, never after generation.
- **G4** — Conversation memory plus long-term user memory, so follow-ups ("what's the exception clause in that one?") work.
- **G5** — Traces, datasets, and evaluators in LangSmith; a regression gate on every PR.
- **G6** — A simple but genuinely usable UI for non-technical staff.

### 2.2 Non-Goals (NG)

- **NG1** — Document **editing** or authoring workflows. Ferret is read-only.
- **NG2** — Fine-tuning or training our own models. Prompting + retrieval only.
- **NG3** — Real-time streaming data (Kafka, DB CDC). Batch/scheduled ingestion is sufficient.
- **NG4** — Multi-tenant SaaS billing. This is a single-organization internal deployment.
- **NG5** — Voice, mobile app, or Slack/Teams bots in v1 (candidates for v2).

---

## 3. Users and Primary Use Cases

| Persona | Need | Representative question |
|---|---|---|
| Support engineer | Fast policy/spec lookup | "How many days is the refund window on the Enterprise plan?" |
| Legal/Compliance | Contract clause comparison | "What's the liability cap in Vendor X's MSA, and how does it differ from our standard template?" |
| New hire | Onboarding | "What is the deployment approval process?" |
| Analyst | Multi-document synthesis | "What have the last three quarterly reports said about churn?" |
| Admin | Source management | Which documents were indexed when, and which ones failed |

**Design-driving observation:** the last two use cases are multi-hop — a single retrieval pass is not enough. That's why query decomposition is in §8.

---

## 4. System Architecture

```
                    ┌──────────────────────────────────────────┐
                    │           Streamlit UI (chat)            │
                    │  chat · sources panel · feedback · admin │
                    └───────────────────┬──────────────────────┘
                                        │ SSE / REST
                    ┌───────────────────▼──────────────────────┐
                    │            FastAPI  (app/api)            │
                    │   authn (OIDC) · authz (ACL) · rate limit│
                    └───────────────────┬──────────────────────┘
                                        │
                    ┌───────────────────▼──────────────────────┐
                    │        LangGraph agent (app/graph)       │
                    │                                          │
                    │  route → (decompose) → retrieve →        │
                    │  rerank → grade → generate → verify      │
                    │            ▲                    │        │
                    │            └──── retry (≤1) ◄───┘        │
                    └────┬──────────────┬──────────────┬───────┘
                         │              │              │
              ┌──────────▼───┐  ┌───────▼──────┐  ┌────▼─────────┐
              │  Retrieval   │  │   Memory     │  │  Claude API  │
              │  pgvector +  │  │ checkpointer │  │  Opus 5      │
              │  tsvector    │  │ + store      │  │  (citations) │
              │  + reranker  │  │  (Postgres)  │  │              │
              └──────▲───────┘  └──────────────┘  └──────────────┘
                     │
       ┌─────────────┴──────────────┐
       │   Ingestion (Celery beat)  │
       │  fetch → parse → chunk →   │
       │  embed → upsert            │
       └───▲────────────────▲───────┘
           │                │
      ┌────┴────┐      ┌────┴─────────┐
      │  PDFs   │      │ Web sources  │
      │ (S3/FS) │      │ (sitemap)    │
      └─────────┘      └──────────────┘

           every node → LangSmith (trace, feedback, dataset)
```

### 4.1 Why this shape

- **One Postgres** — documents, chunks, embeddings (pgvector), BM25 (tsvector), the LangGraph checkpointer, and the LangGraph store. A separate vector DB (Pinecone/Qdrant) adds operational overhead in v1 and makes the ACL join harder. pgvector + HNSW carries us to ~10M chunks; past that, the migration path is in §16.
- **LangGraph** because we need both the retrieve→grade→retry loop and memory persistence — in a plain chain both are hand-rolled.
- **A separate verify node** so groundedness is a runtime gate, not just an offline metric.

---

## 5. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 | LangChain/LangSmith ecosystem |
| Orchestration | LangGraph (`langgraph`, `langchain`) | stateful graph, checkpointer, store |
| LLM | **Claude Opus 5** (`claude-opus-5`) | 1M context, native citations, adaptive thinking |
| Judge LLM | `claude-opus-5` (offline eval), `claude-haiku-4-5` (online sampling) | accuracy offline, cost online |
| Embedding | `text-embedding-3-large` (3072d), Matryoshka-truncated → 1024d | balances pgvector index size against quality |
| Reranker | `bge-reranker-v2-m3` (self-hosted, CPU/GPU) | large precision gain with no external API dependency |
| API | FastAPI + SSE | streaming tokens |
| Store | Postgres 16 + `pgvector` 0.7 + `pg_trgm` | single datastore |
| Queue | Celery + Redis | scheduled crawls, ingestion fan-out |
| PDF parsing | PyMuPDF (fast path) → `unstructured[local-inference]` (scanned/tables) | cost/quality balance |
| UI | Streamlit | fastest path; same repo, same language |
| Observability | LangSmith + OpenTelemetry → Grafana | traces + infra metrics |

> **Note on the UI:** the request was for a "simple UI," so Streamlit — it stands up in a day. If SSO-embedded, branded, or 50+ concurrent users become requirements later, it can be swapped for Next.js with the API contract (§11) unchanged; that swap is the only cost of drawing the boundary here.

### 5.1 Claude API usage rules

```python
# app/llm/client.py — the single path for every call
resp = client.messages.create(
    model="claude-opus-5",
    max_tokens=16000,
    thinking={"type": "adaptive"},          # not budget_tokens — Opus 5 returns 400
    output_config={"effort": "high"},       # "xhigh" for synthesis questions
    system=[
        {"type": "text", "text": SYSTEM_PROMPT,
         "cache_control": {"type": "ephemeral"}},   # stable prefix
    ],
    messages=[...],
)
```

- **No prefill** — assistant prefill returns 400 on Opus 5. Control format via the system prompt or `output_config.format`.
- **Streaming** — every user-facing call uses `client.messages.stream()` + `get_final_message()`.
- **Refusal fallback** — `betas=["server-side-fallback-2026-07-01"]` + `fallbacks="default"`; check `stop_reason == "refusal"` on every response and surface the explanation in the UI.

---

## 6. Data Model

```sql
-- Source registry: a PDF folder, a sitemap, a manual upload
CREATE TABLE sources (
  id            uuid PRIMARY KEY,
  kind          text NOT NULL,          -- 'pdf_bucket' | 'web_sitemap' | 'upload'
  uri           text NOT NULL,
  crawl_config  jsonb NOT NULL DEFAULT '{}',  -- depth, include/exclude regex, cadence
  acl_groups    text[] NOT NULL,        -- source-level default ACL
  enabled       boolean NOT NULL DEFAULT true,
  last_run_at   timestamptz
);

CREATE TABLE documents (
  id            uuid PRIMARY KEY,
  source_id     uuid REFERENCES sources(id) ON DELETE CASCADE,
  uri           text NOT NULL,          -- s3://... or https://...
  title         text,
  content_hash  text NOT NULL,          -- skip re-embedding when unchanged
  page_count    int,
  acl_groups    text[] NOT NULL,        -- document-level override
  metadata      jsonb NOT NULL DEFAULT '{}',  -- author, effective_date, doc_type, version
  indexed_at    timestamptz,
  status        text NOT NULL,          -- 'pending'|'indexed'|'failed'|'stale'
  error         text,
  UNIQUE (source_id, uri)
);

CREATE TABLE chunks (
  id            uuid PRIMARY KEY,
  document_id   uuid REFERENCES documents(id) ON DELETE CASCADE,
  ordinal       int NOT NULL,
  text          text NOT NULL,
  -- locator: PDF {page: 12, bbox: [...]}, web {anchor: "#sla", char_start: 4211}
  locator       jsonb NOT NULL,
  heading_path  text[],                 -- ["Security", "Data Retention"] — context prefix
  token_count   int NOT NULL,
  embedding     vector(1024),
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
CREATE INDEX ON chunks USING gin (tsv);
CREATE INDEX ON documents USING gin (acl_groups);

-- Feedback: UI thumbs → LangSmith, and kept locally too
CREATE TABLE feedback (
  id            uuid PRIMARY KEY,
  run_id        uuid NOT NULL,          -- LangSmith run id
  thread_id     text NOT NULL,
  user_id       text NOT NULL,
  score         int NOT NULL,           -- -1 | +1
  comment       text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
```

LangGraph's own tables (`checkpoints`, `checkpoint_writes`, `store`) live in the same database under a `langgraph` schema.

---

## 7. Ingestion Pipeline

```
discover → fetch → parse → chunk → embed → upsert → mark
```

| Step | Detail |
|---|---|
| **discover** | PDF bucket: S3 `list_objects` delta. Web: sitemap.xml, falling back to BFS crawl (`max_depth=3`, robots.txt respected, `include_patterns` regex). |
| **fetch** | Conditional GET on ETag/Last-Modified; stop here if `content_hash` is unchanged. |
| **parse** | PDF → PyMuPDF (`get_text("dict")`) to get page + bbox. If the text layer is < 100 chars/page, treat as scanned and fall back to `unstructured` + OCR. HTML → `trafilatura` (boilerplate stripped) with the heading tree preserved. |
| **chunk** | Heading-aware recursive split. Target **700 tokens**, overlap **100**. Each chunk is prefixed with its `heading_path` ("Security > Data Retention\n\n…") — this measurably helps retrieval, because a fragment read alone is meaningless. Tables become their own chunks, serialized as markdown. |
| **embed** | Batches of 100, `text-embedding-3-large` → truncated to 1024d. Exponential backoff on rate limits. |
| **upsert** | Delete + reinsert chunks by `document_id` in one transaction, so stale chunks never linger. |
| **mark** | Set `documents.status`, `indexed_at`, and `error` on failure; failed documents surface in the admin view. |

**Schedule:** Celery beat — web sources every 24h, PDF buckets every 6h, manual uploads immediately. Concurrency of 4 workers with a per-source lock so the same crawl never runs twice.

**Idempotency:** `(source_id, uri, content_hash)` — the same triple arriving again is a no-op. That is what makes the whole pipeline safe to re-run.

---

## 8. Retrieval Pipeline

```
query → [decompose?] → parallel(dense, sparse) → RRF fuse → ACL filter
      → rerank → context pack → grade
```

**8.1 Query decomposition** — a router node decides whether the question is simple or multi-hop. If multi-hop, Opus 5 produces 2–4 sub-queries, each retrieved separately and then unioned. If simple, go straight through (saving an LLM call).

**8.2 Hybrid search** — in a single SQL round trip:

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
SELECT id, SUM(1.0 / (60 + rank)) AS rrf   -- Reciprocal Rank Fusion, k=60
FROM (SELECT * FROM dense UNION ALL SELECT * FROM sparse) u
GROUP BY id ORDER BY rrf DESC LIMIT 30;
```

> **ACL belongs in the innermost WHERE** — this is not negotiable. Filtering later means unauthorized text enters the prompt, and at that point the leak is prevented only by the model's good behavior.

**8.3 Rerank** — 30 candidates → `bge-reranker-v2-m3` → top **8**. Without this step hybrid has high recall but low precision, and precision is what determines groundedness.

**8.4 Context packing** — each chunk is its own `document` content block, so Claude's citation locators map back to our chunks:

```python
docs = [{
    "type": "document",
    "source": {"type": "content",
               "content": [{"type": "text", "text": ch.text}]},
    "title": f"{ch.doc_title} — {' > '.join(ch.heading_path)}",
    "context": json.dumps({"uri": ch.uri, "locator": ch.locator}),
    "citations": {"enabled": True},
} for ch in top_k]
```

In the response, `citations[].document_index` on each cited text block → our chunk → its `locator` → a deep link to the PDF page or web anchor in the UI. **Citations are therefore API-guaranteed rather than model-generated** — a hallucinated citation is categorically impossible.

**8.5 Grade** — a binary grade from Haiku 4.5 on whether the retrieved chunks are sufficient for the question. On "no," rewrite the query and retry once; on a second "no," return **"I couldn't find enough information"** plus what was found. At most 1 retry — that is what the latency budget allows.

---

## 9. Generation and Citations

**System prompt (stable, cached):**

```
You are an enterprise document assistant. Rules:
1. Answer only from the provided documents. If the answer isn't there, say so.
2. Every factual claim must be cited.
3. If sources conflict, present both; do not resolve the conflict yourself.
4. When documents carry dates, prefer the most recent, but mention the older one.
5. Answer in the language the question was asked in.
```

**Prompt cache layout** — rendering order is `tools` → `system` → `messages`, so: breakpoint after the stable system prompt; then the long-term memory block; and finally the retrieved documents plus the question (which change per request, hence after the last breakpoint). `usage.cache_read_input_tokens` is exported as a metric — a persistent zero means the prefix is being broken.

**Verify node** — programmatically checks that each sentence in the answer carries a citation (hedging sentences excluded). Any uncited factual sentence sets a `groundedness_violation` flag on the run; the UI renders that passage with a warning and auto-feedback is sent to LangSmith.

---

## 10. Memory

Two tiers, following LangGraph's checkpointer/store split:

**10.1 Short-term (thread)** — `AsyncPostgresSaver` checkpointer keyed by `thread_id`. Holds the full message history plus graph state, which is what makes follow-ups and "explain that last part again" work. Past 40 messages, the older span is summarized into a single system note to keep context spend bounded.

**10.2 Long-term (user)** — `AsyncPostgresStore` with semantic search, namespace `("memories", user_id)`:

```python
store = AsyncPostgresStore.from_conn_string(
    DB_URI, index={"embed": embeddings, "dims": 1024}
)
# retrieve
mems = await runtime.store.asearch(("memories", user_id),
                                   query=latest_user_msg, limit=5)
# write — from the extraction node
await runtime.store.aput(("memories", user_id), str(uuid4()),
                         {"data": fact, "source_thread": thread_id})
```

**What gets remembered (extraction policy):** role and team, active projects/vendors, format preferences (e.g. "always use bullets"), recurring topics. **What does not:** document content (that's RAG's job), and any personal or sensitive detail the user did not state explicitly.

At the end of each turn a cheap extraction call (Haiku 4.5) proposes candidate facts; a semantic near-duplicate in the same namespace is merged, otherwise the fact is inserted.

**Control:** a "what Ferret knows about me" panel in the UI — view the list, delete individually, or clear everything. This is also the mechanism for GDPR erasure requests.

---

## 11. API Contract

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/chat` | question → SSE stream |
| `GET` | `/v1/threads` | user's thread list |
| `GET` | `/v1/threads/{id}` | full history |
| `DELETE` | `/v1/threads/{id}` | delete a thread |
| `GET` | `/v1/memories` | list long-term memories |
| `DELETE` | `/v1/memories/{id}` | delete one memory |
| `POST` | `/v1/feedback` | `{run_id, score, comment}` → LangSmith + DB |
| `GET` | `/v1/sources` | admin: sources and index status |
| `POST` | `/v1/sources/{id}/reindex` | admin: manual trigger |
| `POST` | `/v1/documents` | admin: manual PDF upload |
| `GET` | `/healthz`, `/readyz` | liveness / readiness |

**`POST /v1/chat` request:**

```json
{ "thread_id": "uuid | null",
  "message": "How many days is the refund window on the Enterprise plan?",
  "filters": { "doc_type": ["policy"], "effective_after": "2025-01-01" } }
```

**SSE events:** `status` (retrieving/reranking/generating) → `sources` (chunk metadata, sent before tokens so the UI panel fills first) → `token`* → `citation` → `done` (`run_id`, `usage`, `latency_ms`) | `error`.

---

## 12. UI

**Chat page** — message list; citations inline as superscripts `[1]`, hover shows the `cited_text` snippet, click opens the PDF page or web anchor in the right panel. Input box below with filter dropdowns (doc_type, date). Every answer carries 👍/👎 plus an optional comment.

**Sources panel** — which 8 chunks were used, with rerank scores. Transparency builds trust, and this is also the single most useful debugging surface.

**Memory panel** — the list/delete controls from §10.

**Admin tab** (role-gated) — source table, last crawl time, document counts, failed documents with errors, a "Reindex now" button, and the upload form.

**Empty state** — 4 example questions, because a new user has no idea what the system knows.

---

## 13. LangSmith Evaluation

### 13.1 Datasets

| Dataset | Size | Composition |
|---|---|---|
| `ferret-golden-qa` | 150 | SME-written question + reference answer + expected `document_id` list |
| `ferret-multihop` | 40 | Questions requiring 2+ documents |
| `ferret-refusal` | 30 | Questions **not** covered by the corpus — the correct answer is "I don't know" |
| `ferret-adversarial` | 30 | Prompt injection, ACL probing, ambiguous questions |
| `ferret-prod-sampled` | ongoing | 20/week sampled from production (👎 prioritized), SME-labeled and promoted into golden |

Keeping `refusal` and `adversarial` as separate sets matters — without them, eval only rewards confident answering.

### 13.2 Evaluators

```python
# eval/evaluators.py
from langsmith import Client, evaluate
from typing_extensions import Annotated, TypedDict

class CorrectnessGrade(TypedDict):
    explanation: Annotated[str, ..., "Reasoning for the score"]
    correct: Annotated[bool, ..., "True if correct relative to the reference"]

grader = init_chat_model("claude-opus-5").with_structured_output(CorrectnessGrade)

def correctness(inputs: dict, outputs: dict, reference_outputs: dict) -> bool:
    """Factual accuracy relative to the reference answer."""
    grade = grader.invoke([
        {"role": "system", "content": CORRECTNESS_INSTRUCTIONS},
        {"role": "user", "content":
            f"QUESTION: {inputs['question']}\n"
            f"GROUND TRUTH: {reference_outputs['answer']}\n"
            f"STUDENT ANSWER: {outputs['answer']}"},
    ])
    return grade["correct"]

def groundedness(inputs: dict, outputs: dict) -> bool:
    """Whether every claim in the answer is supported by the retrieved chunks (LLM judge)."""

def retrieval_recall(outputs: dict, reference_outputs: dict) -> float:
    """Fraction of expected document_ids that made it into top-k — deterministic, no LLM."""
    expected = set(reference_outputs["document_ids"])
    got = {c["document_id"] for c in outputs["chunks"]}
    return len(expected & got) / len(expected) if expected else 1.0

def citation_validity(outputs: dict) -> float:
    """Whether each cited_text is genuinely a substring of its source chunk — deterministic."""

def refusal_accuracy(outputs: dict, reference_outputs: dict) -> bool:
    """On the refusal set: did the system actually refuse?"""

evaluate(
    target_fn, data="ferret-golden-qa",
    evaluators=[correctness, groundedness, retrieval_recall,
                citation_validity, refusal_accuracy],
    experiment_prefix="ferret-opus5-hybrid-rerank",
    max_concurrency=8,
    metadata={"models": ["claude-opus-5"], "retriever": "hybrid+bge-rerank",
              "chunk_tokens": 700, "top_k": 8},
)
```

Two evaluators are **deliberately deterministic** (`retrieval_recall`, `citation_validity`) — they catch most regressions with no judge cost, and their verdicts are not arguable.

### 13.3 Regression gate (CI)

`.github/workflows/eval.yml` — every PR touching retrieval, prompts, or the graph runs `ferret-golden-qa` (150) + `ferret-refusal` (30):

| Metric | Minimum | Max drop vs. main |
|---|---|---|
| correctness | 0.85 | −0.02 |
| groundedness | 0.95 | −0.01 |
| retrieval_recall@8 | 0.90 | −0.02 |
| citation_validity | 0.99 | 0 |
| refusal_accuracy | 0.90 | −0.03 |
| p95 latency | ≤ 6000 ms | +15% |

A broken gate blocks the PR; the LangSmith comparison view link is posted as a PR comment. Cost: ~$4 per run, once per PR.

### 13.4 Production feedback loop

Every run is `@traceable` into LangSmith (with `user_id`, `thread_id`, `source_ids`, `latency`, `usage` metadata). UI 👍/👎 goes through `client.create_feedback(run_id, ...)`. 5% of traffic is sampled by an online groundedness judge (Haiku 4.5). Weekly: review 👎 runs → add to the golden set → the §13.3 gate protects that case from then on.

---

## 14. Observability

- **LangSmith** — per-node traces; the retrieval node logs candidates and scores, so "why did this chunk surface?" is answerable from the trace itself.
- **Metrics (Prometheus)** — `ferret_query_latency_seconds{stage}`, `ferret_retrieval_candidates`, `ferret_cache_read_tokens`, `ferret_tokens_total{kind}`, `ferret_ingest_docs_total{status}`, `ferret_groundedness_violations_total`.
- **Alerts** — p95 > 8s (5 min), ingestion failure > 5%, groundedness violations > 2%, `cache_read_input_tokens` persistently zero, daily spend > 150% of budget.
- **Logs** — structured JSON with `run_id` as the correlation key; full question text lives in a separate retention class (§15).

---

## 15. Security and Compliance

| Concern | Decision |
|---|---|
| Authn | OIDC (Okta/Entra), JWT; UI and API share one issuer |
| Authz | JWT group claim → `user_groups` → the WHERE clause of every retrieval query (§8.2). ACL tests are part of the eval suite. |
| Prompt injection | Document content is **data, not instructions** — stated in the system prompt, and structurally separated by being sent as `document` blocks; the `ferret-adversarial` set measures it. |
| Data residency | `inference_geo="us"` (or the organization's region) on every Messages call |
| Retention | threads 90 days (configurable), memories user-controlled, LangSmith traces 30 days |
| PII | Optional PII scan at ingestion; flagged documents land in a restricted ACL group |
| Secrets | env vars / vault; never in code |
| Rate limits | 20 questions/min/user, 5 concurrent |
| Audit | Who got an answer from which document — immutable log keyed by `run_id` |

---

## 16. Performance and Cost

**Latency budget (p95, 6 seconds):**

| Stage | Budget |
|---|---|
| Embed query | 150 ms |
| Hybrid SQL | 250 ms |
| Rerank (30 → 8) | 400 ms |
| Grade (Haiku) | 500 ms |
| Generate (Opus 5, first token) | 1200 ms |
| Generate (full, streamed) | 3000 ms |
| Overhead | 500 ms |

**Cost per question (estimated):** ~12K input tokens (8 chunks + system + memory), ~600 output tokens. Opus 5 at $5/$25 per MTok → **~$0.075**, or **~$0.055** when the cached system prefix hits. At 1,000 questions/day ≈ **$55–75/day**, plus embeddings (~$0.15/day of ingestion) and eval (~$4/PR).

**Cost-reduction order** (if needed, in this order): verify caching is actually working → `effort: "low"` on simple questions → chunk count 8 → 6 → route easy questions to Sonnet 5. **Model downgrade is the last step**, and the §13.3 gate must be run after each one.

**Scale ceiling:** pgvector + HNSW holds p95 < 300ms up to ~10M chunks (≈ 200K documents) on 8 vCPU / 32GB. Beyond that: first partition on `documents.acl_groups`/`doc_type`; if that isn't enough, move only the vectors to Qdrant, leaving the rest of the schema untouched.

---

## 17. Deployment

Docker Compose (dev) → Kubernetes (prod). Components: `api` (3 replicas), `worker` (2), `beat` (1), `ui` (2), `reranker` (1, ideally on a GPU node), `postgres` (managed), `redis` (managed).

Migrations: Alembic. Deploy gates: `pytest` → the `eval` job (§13.3) → staging smoke → rolling prod rollout. Rollback: previous image + Alembic downgrade (all v1 migrations must stay backward-compatible).

---

## 18. Repo Structure

```
ferret/
├── app/
│   ├── api/          # FastAPI routes, SSE, auth middleware
│   ├── graph/        # LangGraph nodes: route, retrieve, rerank, grade, generate, verify
│   ├── ingest/       # discover, fetch, parse, chunk, embed, upsert
│   ├── llm/          # Anthropic client wrapper, prompts, cache layout
│   ├── memory/       # checkpointer + store setup, extraction
│   ├── retrieval/    # hybrid SQL, RRF, reranker client
│   └── models/       # SQLAlchemy models, Alembic migrations
├── ui/               # Streamlit app
├── eval/             # datasets/, evaluators.py, run_eval.py
├── tests/            # unit + integration (testcontainers Postgres)
├── deploy/           # Dockerfiles, compose, k8s manifests
└── SPEC.md
```

---

## 19. Milestones

| # | Name | Scope | Duration | Exit criteria |
|---|---|---|---|---|
| M0 | Skeleton | repo, Postgres+pgvector, CI, LangSmith project | 3 days | `/healthz` green, traces visible in LangSmith |
| M1 | Ingestion | PDF + web, chunk, embed, admin view | 1.5 weeks | 500 docs indexed, re-run idempotent |
| M2 | Naive RAG | dense-only retrieval, generate + citations | 1 week | end-to-end answers with citations |
| M3 | Eval harness | 50-question golden set, 5 evaluators, CI gate | 1 week | baseline numbers recorded |
| M4 | Retrieval v2 | hybrid + RRF + rerank + grade/retry | 1.5 weeks | recall@8 ≥ 0.90, measured gain over M2 |
| M5 | Memory | checkpointer + store + extraction + UI panel | 1 week | follow-ups work, memory deletion works |
| M6 | UI + ACL | full Streamlit, OIDC, ACL filtering | 1.5 weeks | ACL tests pass, adversarial set passes |
| M7 | Hardening | multi-hop, remaining datasets, alerts, load test | 1.5 weeks | every condition in §21 met |

Total ≈ **10 weeks** with 2 engineers. M3 sits before M4 deliberately — tuning retrieval without eval is throwing stones in the dark.

---

## 20. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Poor OCR quality on scanned PDFs | Wrong answers | Text-layer detection + OCR fallback; low-confidence docs flagged in the admin view |
| SME time for the golden set never materializes | Eval is meaningless | Start with 50 questions at M3; first draft LLM-generated, SMEs only review |
| ACL groups drift from the HR system | Data exposure | Nightly group sync; fail closed on unmatched groups |
| Multi-hop questions perform poorly | Analyst persona frustrated | Decomposition at M7; measured on `ferret-multihop` |
| Cost overruns | Budget | Daily budget alert + the reduction order in §16 |
| Hitting the pgvector ceiling | Latency collapse | Migration path in §16, schema unchanged |

---

## 21. Acceptance Criteria

v1 is "done" only when all of these hold:

1. 5,000+ documents (PDF + web) indexed, scheduled re-indexing running, failed docs visible in the admin view.
2. All six gate metrics from §13.3 at threshold, and the gate demonstrably blocks a PR in CI (proven with a deliberate regression).
3. A clickable citation next to every factual claim that lands on the correct PDF page or web anchor.
4. ACL: two users in different groups get different (correct) answers to the same question; restricted document content does not appear even in the unauthorized user's trace.
5. Follow-up questions work; users can view and delete their long-term memories.
6. p95 latency ≤ 6s, load-tested at 20 concurrent users.
7. Every production run traced in LangSmith; UI feedback arrives there.
8. Runbook written: ingestion failure, latency spike, cost spike, ACL issues.

---

## 22. Open Questions

1. **Web source list** — which internal sites/Confluence spaces are in v1? Crawl or API export?
2. **Source of truth for ACLs** — Okta groups, or a separate document management system?
3. **Language** — does the corpus contain non-English documents? If so the embedding model needs reconsidering (multilingual-e5 or Cohere multilingual), since `text-embedding-3-large` is weaker outside English.
4. **Share of scanned PDFs** — above 30% and the OCR pipeline moves into M1 rather than M7.
5. **SME availability** — how many hours per week for golden-set labeling?
6. **Is on-prem mandatory?** — if so both the reranker and embeddings must be self-hosted, which changes the cost model in §16.
