---
name: eval-gate
description: Run the LangSmith regression gate and produce the numbers block for a PR description. Use whenever a change touches app/retrieval/, app/llm/prompts/, or app/graph/ — CLAUDE.md's definition of done requires gate numbers in the PR.
---

# Run the eval gate

The gate is the only signal that a retrieval, prompt, or graph change actually helped. Infra metrics stay green while answers get worse, so this is not optional for those paths.

## Before running

1. Confirm the change is complete and `pytest -q` passes. A gate run on broken code costs ~$4 and tells you nothing.
2. Confirm `LANGSMITH_API_KEY` and `ANTHROPIC_API_KEY` are set. If `ANTHROPIC_API_KEY` is unset, run `ant auth status` — an active profile works without the env var.
3. Get the baseline. If `main`'s numbers aren't already recorded in the last gate run on the branch point, you need them to compute deltas.

## Run

```bash
python -m eval.run_eval --gate          # golden-qa (150) + refusal (30), ~6 min, ~$4
```

For a narrower loop while iterating (does **not** substitute for the gate):

```bash
python -m eval.run_eval --dataset ferret-golden-qa --limit 30
```

## Thresholds

| Metric | Minimum | Max drop vs. main |
|---|---|---|
| correctness | 0.85 | −0.02 |
| groundedness | 0.95 | −0.01 |
| retrieval_recall@8 | 0.90 | −0.02 |
| citation_validity | 0.99 | 0 |
| refusal_accuracy | 0.90 | −0.03 |
| p95 latency | ≤ 6000 ms | +15% |

## Report

Paste into the PR description, filling real numbers — never estimates, never "expected to improve":

```
### Eval gate
| metric | main | this PR | Δ |
|---|---|---|---|
| correctness        | 0.87 | 0.89 | +0.02 |
| groundedness       | 0.96 | 0.96 |  0.00 |
| retrieval_recall@8 | 0.91 | 0.94 | +0.03 |
| citation_validity  | 1.00 | 1.00 |  0.00 |
| refusal_accuracy   | 0.93 | 0.90 | −0.03 |
| p95 latency (ms)   | 5100 | 5400 | +6%   |

LangSmith comparison: <url>
```

## Interpreting failures

- **`citation_validity` below 1.0** — a bug in `app/llm/citations.py`, never noise. Cited text either is or isn't a substring of its chunk. Stop and fix before looking at anything else.
- **`retrieval_recall` up, `correctness` flat** — retrieval improved but generation isn't using it. Look at context packing order and top-k, not the retriever.
- **`groundedness` down, `correctness` up** — the model is answering from parametric knowledge. This is the worst failure mode in this product; treat it as blocking even if correctness looks better.
- **`refusal_accuracy` down after a retrieval change** — better recall is surfacing weak matches for out-of-corpus questions. The grade node's threshold likely needs raising, not the retriever reverting.
- **Latency up, quality flat** — revert. There's no credit for spending the budget without moving a metric.

## Rules

- Report what the run produced, including regressions. A gate failure reported honestly is worth more than a passing run on a narrowed dataset.
- Never widen a threshold to make a change pass. Thresholds change only in their own PR, with a stated reason.
- Don't run the gate on every push — it costs money each time.
