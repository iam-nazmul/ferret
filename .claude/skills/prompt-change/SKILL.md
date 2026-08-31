---
name: prompt-change
description: Safely edit a prompt in app/llm/prompts/. Use for any change to system prompts, grading prompts, decomposition, or memory extraction — prompt edits are the highest-variance change in this repo and the easiest to regress silently.
---

# Change a prompt

Prompts are the highest-leverage and lowest-visibility code in Ferret. A one-word edit can move groundedness by several points with no test failure anywhere.

## Rules

1. **Prompts live only in `app/llm/prompts/`** as named constants. If you find a prompt string inline in a node or route, moving it here is part of the fix.
2. **Never interpolate per-request data into `ANSWER_SYSTEM_PROMPT`** — not a date, not a user id, not a filter description. It sits behind the `cache_control` breakpoint; one variable byte invalidates the prefix and raises cost ~35% with no error.
3. **Volatile content goes in `messages`**, after the last breakpoint. Order is `tools` → `system` → `messages`.
4. Edits to the five answer rules in `ANSWER_SYSTEM_PROMPT` are behavior changes, not wording changes. Treat them as such.

## Procedure

1. Edit the constant in `app/llm/prompts/`.
2. Check the prefix is still stable — the constant must be a literal, not an f-string or a `.format()` call.
3. Run the gate:
   ```bash
   python -m eval.run_eval --gate
   ```
4. **Verify caching still works.** After the run, `usage.cache_read_input_tokens` must be non-zero on repeat calls; the exported metric is `ferret_cache_read_tokens`. A persistent zero means something volatile drifted into the prefix — that's a bug in this change, not a tuning issue.
5. Put the gate numbers in the PR description (see the `eval-gate` skill).

## What tends to go wrong

- **Adding "be concise"** reliably drops `correctness` on multi-part questions — the model drops the second half of the answer.
- **Weakening rule 1** ("answer only from the provided documents") raises correctness and drops groundedness, because the model starts filling gaps from training data. Always check both metrics together; a correctness gain alone is not a win here.
- **Adding citation instructions** is a no-op at best. Citations come from the API via `document` blocks, not from the model writing markers. If you're tempted to prompt for citation formatting, the actual bug is in `app/llm/documents.py` or `citations.py`.
- **Reordering rules** changes behavior more than expected. If you reorder, run the gate; don't assume it's cosmetic.

## Multilingual

Rule 5 ("answer in the language the question was asked in") is load-bearing — the corpus and users may not share a language. Don't remove it while "simplifying," and if you change it, check the gate's non-English examples specifically.
