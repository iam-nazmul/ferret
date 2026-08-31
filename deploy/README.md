# deploy — containers, compose, Kubernetes

Local stack and production manifests.

Spec: [SPEC.md §17](../../SPEC.md).

```
Dockerfile.api        # api + worker + beat (same image, different command)
Dockerfile.ui         # Streamlit
Dockerfile.reranker   # bge-reranker-v2-m3 service
compose.yml           # local dev: postgres, redis, reranker (+ optional app)
k8s/                  # base/ and overlays/{staging,prod}
```

## Local

```bash
docker compose -f deploy/compose.yml up -d postgres redis reranker
```

Run the app processes on the host (see [CLAUDE.md](../CLAUDE.md)) — reload works, and only the dependencies live in containers.

## Components in prod

| Component | Replicas | Notes |
|---|---|---|
| `api` | 3 | stateless; HPA on CPU + request rate |
| `worker` | 2 | Celery; separate queue for OCR-heavy sources |
| `beat` | **1** | never scale this — duplicate schedulers double-crawl |
| `ui` | 2 | stateless |
| `reranker` | 1 | GPU node if available; CPU works within budget |
| `postgres` | managed | pgvector extension required |
| `redis` | managed | Celery broker |

## Deploy pipeline

```
pytest → eval gate (§13.3) → staging smoke → prod rolling
```

**The eval gate is a deploy gate, not just a PR gate.** A retrieval regression that reaches prod is invisible in every infra metric — latency and error rates stay green while the answers get worse.

Rollback: previous image + `alembic downgrade -1`. This only works because v1 migrations are backward-compatible (see `app/models/README.md`) — that constraint exists to make this command safe.

## Configuration

Everything from env, read once through `app/config.py`. Secrets from the cluster secret store, never in manifests or images. Required: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `RERANKER_URL`, `OIDC_ISSUER`, `OIDC_GROUP_CLAIM`.

## Probes

- `api`: liveness `/healthz` (process only), readiness `/readyz` (DB + reranker).
  **Do not point liveness at `/readyz`** — a slow database then restarts every pod, turning degradation into an outage.
- `reranker`: readiness only after the model is loaded; cold start is ~30s.
- `worker`: no HTTP probe; use Celery's ping.

## Gotchas

- Beat at 2 replicas double-crawls every source. It's the most expensive one-character mistake available here.
- The reranker image is large (~2GB). Pre-pull on nodes or the first pod schedule looks like an outage.
- Postgres connection limits: `api` (3 × pool) + `worker` (2 × pool) + migrations. Size the pools deliberately; the default will exhaust a small managed instance.
- Long SSE responses need proxy read timeouts above 60s and buffering disabled, or answers arrive all at once at the end.
