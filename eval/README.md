# eval — LangSmith datasets, evaluators, CI gate

Offline evaluation and the regression gate. **`eval` treats the graph as a black box** — it imports `app.graph` and calls it like a client, nothing deeper. That is what makes its numbers mean something about the system users get.

Spec: [SPEC.md §13](../../SPEC.md).

## Layout

```
run_eval.py     # CLI: --dataset <name> | --gate
evaluators.py   # the five evaluators
target.py       # graph → the (inputs → outputs) callable evaluate() expects
datasets/       # seed JSONL, one file per dataset
sync.py         # push datasets/ to LangSmith, idempotent
gate.py         # thresholds + comparison against main
```

## Datasets

| Dataset | Size | What it protects |
|---|---|---|
| `ferret-golden-qa` | 150 | core correctness and retrieval |
| `ferret-multihop` | 40 | questions needing 2+ documents |
| `ferret-refusal` | 30 | saying "I don't know" when the corpus doesn't cover it |
| `ferret-adversarial` | 30 | prompt injection, ACL probing, ambiguity |
| `ferret-prod-sampled` | ongoing | 20/week from production, 👎 prioritized |

**`refusal` and `adversarial` are separate on purpose.** Folded into the golden set, they'd be ~20% of it and a model that answers everything confidently would still score well. Kept separate with their own thresholds, over-confidence is visible.

## Evaluators

```python
def correctness(inputs, outputs, reference_outputs) -> bool   # LLM judge (Opus 5)
def groundedness(inputs, outputs) -> bool                     # LLM judge
def retrieval_recall(outputs, reference_outputs) -> float     # deterministic
def citation_validity(outputs) -> float                       # deterministic
def refusal_accuracy(outputs, reference_outputs) -> bool      # deterministic
```

**Prefer deterministic evaluators.** Three of the five are: they're free, fast, reproducible, and nobody argues with their verdicts. Reach for an LLM judge only when the property genuinely requires reading — "is this answer correct" does, "is this cited_text a substring of its chunk" does not.

Signature matters: LangSmith injects by parameter name (`inputs`, `outputs`, `reference_outputs`). Rename a parameter and you get a confusing runtime error.

## The gate

```bash
python -m eval.run_eval --gate     # golden-qa + refusal, ~$4, ~6 min
```

| Metric | Minimum | Max drop vs. main |
|---|---|---|
| correctness | 0.85 | −0.02 |
| groundedness | 0.95 | −0.01 |
| retrieval_recall@8 | 0.90 | −0.02 |
| citation_validity | 0.99 | 0 |
| refusal_accuracy | 0.90 | −0.03 |
| p95 latency | ≤ 6000 ms | +15% |

Runs on every PR touching `app/retrieval/`, `app/llm/prompts/`, or `app/graph/`. **Put the numbers in the PR description** — a reviewer should not have to open LangSmith to see whether a retrieval change helped.

`citation_validity` has zero tolerance: cited text either is or isn't in the source chunk. Any drop is a bug in `app/llm/citations.py`, not noise.

## Extending

**New evaluator:** add to `evaluators.py`, wire into `run_eval.py`. If it's going into the gate, run it on main first to establish a baseline — a threshold picked without one is a guess that will either never fire or block everything.

**New dataset:** JSONL in `datasets/`, then `python -m eval.sync`. Sync is idempotent; re-running does not duplicate examples.

**Growing golden from production:** weekly, pull 👎 runs, have an SME write the reference answer and expected `document_id`s, append to `datasets/golden.jsonl`. Every fixed bug should end up here — that's what stops it coming back.

## Gotchas

- `evaluate()` runs the target concurrently (`max_concurrency=8`). The target must be safe to run in parallel with distinct `thread_id`s, or memory bleeds between examples and the results are garbage.
- The judge model is pinned in `evaluators.py`. Changing it re-baselines everything — treat it as a dataset change, not a code change.
- Every gate run costs money. Don't put it on a push-to-any-branch trigger.
- An example with no expected `document_id`s makes `retrieval_recall` vacuously 1.0. `sync.py` rejects those.
