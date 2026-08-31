# app/api — HTTP surface

FastAPI app: routing, authentication, authorization, SSE streaming. **This layer owns the security boundary.** Everything below it assumes `user_groups` has already been established and is trustworthy.

Spec: [SPEC.md §11](../../SPEC.md), [§15](../../SPEC.md).

## Layout

```
main.py         # app factory, middleware order, lifespan (DB pool, graph compile)
deps.py         # FastAPI dependencies: principal, db session, graph handle
auth.py         # OIDC discovery, JWT verification, claim → user_groups mapping
sse.py          # event serialization for the chat stream
schemas.py      # Pydantic request/response models
ratelimit.py    # per-user throttling, applied before the graph runs
routes/
  chat.py       # POST /v1/chat — the only streaming endpoint
  threads.py    # GET/DELETE /v1/threads
  memories.py   # GET/DELETE /v1/memories
  feedback.py   # POST /v1/feedback
  admin.py      # sources, reindex, upload — role-gated
  health.py     # /healthz, /readyz
```

## Contracts

**`Principal`** (`deps.py`) is what every route works with:

```python
class Principal(BaseModel):
    user_id: str
    groups: frozenset[str]   # from the JWT group claim, never from the request
    is_admin: bool
```

**Never accept `user_groups`, `user_id`, or any ACL input from the request body or query string.** If a caller could pass it, a caller could forge it. This is the single most important rule in this module.

**SSE event order** on `/v1/chat` is fixed and the UI depends on it:

```
status(retrieving) → status(reranking) → sources[...] → status(generating)
→ token* → citation* → done{run_id, usage, latency_ms}
```

`sources` is emitted **before** the first token so the panel fills while the answer streams. Any error at any point becomes a terminal `error` event — the stream must never just stop. Send an SSE comment heartbeat (`: ping`) every 15s so proxies don't close idle connections during a slow retrieval.

`done.run_id` is the LangSmith run id; the UI feeds it back to `POST /v1/feedback`, so it must be the real one, not a locally generated id.

## Invariants

- Routes are thin. Business logic belongs in `app/graph/`. A route that is more than ~30 lines is probably doing someone else's job.
- Admin routes check `principal.is_admin` via a dependency, never inline in the handler body.
- Rate limits (20 q/min/user, 5 concurrent) are middleware, applied before the graph is invoked — a rejected request must not cost an LLM call.
- Health: `/healthz` is liveness only (process up). `/readyz` checks DB and reranker reachability. Don't let `/healthz` touch the database or a slow DB will trigger a restart loop.

## Extending

**New endpoint:** route module in `routes/`, schema in `schemas.py`, register in `main.py`. Take `Principal` as a dependency even if you think you don't need it — you need it for the audit log.

**New SSE event type:** add to `sse.py`, add to the table above, and update `ui/` in the same PR. The UI ignores unknown event types by design, so a mismatch fails silently — which is exactly why they ship together.

## Gotchas

- `StreamingResponse` swallows exceptions raised after the first byte. Wrap the generator body and convert failures into an `error` event yourself.
- OIDC JWKS must be cached with a TTL. Fetching per request adds ~100ms and will rate-limit you at the IdP.
- Group claims differ per IdP (`groups`, `roles`, `cognito:groups`). The claim name is config, not a constant.
