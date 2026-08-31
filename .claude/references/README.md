# .claude/references

Verified API facts and project-specific reference material, for agents and developers. Skills and agent definitions link here instead of restating details, so there's one place to correct when an API moves.

| File | Covers | Source |
|---|---|---|
| [claude-api.md](claude-api.md) | model IDs, adaptive thinking, citations, prompt caching, refusal handling | Anthropic docs, 2026-08 |
| [langsmith-eval.md](langsmith-eval.md) | evaluator signatures, `evaluate()`, datasets, tracing, feedback | LangChain docs, 2026-08 |
| [langgraph-memory.md](langgraph-memory.md) | checkpointer vs. store, `Runtime`, state merge semantics | LangGraph docs, 2026-08 |
| [pgvector-hybrid.md](pgvector-hybrid.md) | the hybrid query, operators, HNSW, migrations | project + pgvector docs |

**These are snapshots.** Where a file's content contradicts current official documentation, the live docs win — fetch them, then correct the file in the same change. Where it contradicts something you recall from training, this file wins: several of these APIs changed in 2025–2026.

Ferret invariants live in [CLAUDE.md](../../CLAUDE.md) and the module READMEs, not here. This directory is for external API facts.
