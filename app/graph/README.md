# app/graph — LangGraph orchestration

The agent itself: route → decompose → retrieve → rerank → grade → generate → verify, with a single retry loop. **This is the only module that knows the full shape of a request.** It composes `retrieval`, `memory`, and `llm`; it does not reimplement them.

Spec: [SPEC.md §8](../../SPEC.md), [§9](../../SPEC.md).

## Layout

```
build.py        # graph construction, checkpointer + store wiring, compile()
state.py        # the State TypedDict — the contract between nodes
cli.py          # python -m app.graph.cli "question" --user-groups a,b
#               rewrite() lives in build.py, beside the edge that calls it
nodes/
  route.py      # simple vs multi-hop classification
  decompose.py  # multi-hop → 2-4 sub-queries
  retrieve.py   # calls app.retrieval, per sub-query, unions
  rerank.py     # 30 → top 8
  grade.py      # binary sufficiency check, drives the retry edge
  generate.py   # calls app.llm with document blocks
  verify.py     # citation coverage check
```

## State

```python
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    user_groups: frozenset[str]     # passed in, never derived here
    filters: dict                   # doc_type, effective_after
    sub_queries: list[str]
    candidates: list[Chunk]         # post-fusion, pre-rerank
    chunks: list[Chunk]             # post-rerank, what generation sees
    memories: list[str]
    retry_count: int                # hard cap 1 — see below
    citations: list[Citation]
    groundedness_violation: bool
```

**Nodes are pure functions of state.** No global mutation, no module-level clients that hold request context. This is what makes the graph testable node-by-node and safe to run concurrently.

## Invariants

- **`retry_count` caps at 1.** The latency budget (§16) allows exactly one extra retrieval round trip. If you're tempted to raise it, the fix is better retrieval, not more retries.
- **`user_groups` enters at the API layer and is read-only here.** No node may widen it.
- **Nodes must not build prompt strings.** Import a constant from `app/llm/prompts/`. A node that concatenates instructions inline breaks prompt caching and hides the change from eval diffs.
- **`verify` never blocks the answer.** It sets `groundedness_violation` and lets the response through with a warning. A hard block turns a degraded answer into an outage.
- Every node is a LangSmith span with its inputs and outputs logged. `retrieve` additionally logs candidate ids and scores — without that, "why this chunk?" is unanswerable after the fact.

## Extending

**New node:** function in `nodes/`, add to `build.py`, extend `State` if it produces something. Ask first whether it belongs in the graph or in `retrieval`/`llm` — the graph is for *sequencing*, not for logic that could stand alone.

**New edge condition:** conditional edges live in `build.py`, not scattered as returns inside nodes. Keeping topology in one file is what makes the graph readable a year from now.

**Changing the retry policy or node order:** run `python -m eval.run_eval --gate` and put the numbers in the PR. This is the highest-leverage code in the repo and regressions here are invisible without eval.

## Gotchas

- The checkpointer serializes `State`. Anything you put in it must be JSON-serializable — a `Chunk` dataclass is fine, an open DB connection is not.
- `add_messages` merges by id. Constructing a new message with the same id as an existing one replaces it rather than appending, which is occasionally what you want and usually a bug.
- Node exceptions abort the run and lose the partial answer. Nodes that call external services (`rerank`, `grade`) should degrade — return the input unchanged and log — rather than raise.
