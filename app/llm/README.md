# app/llm — Claude client and prompts

The single path to the Anthropic API. **Every prompt in the system lives here**, and every model call goes through `client.py`. Nothing else in the repo imports `anthropic` directly.

Spec: [SPEC.md §5.1](../../SPEC.md), [§9](../../SPEC.md).

## Layout

```
client.py       # the wrapper: request construction, streaming, error mapping
models.py       # ANSWER_MODEL, JUDGE_MODEL, GRADE_MODEL constants
cache.py        # cache_control placement — the prefix layout
documents.py    # Chunk → document content block with citations enabled
citations.py    # response citations → our Citation type via locator lookup
prompts/
  system.py     # ANSWER_SYSTEM_PROMPT (stable, cached)
  grade.py      # sufficiency grading
  decompose.py  # sub-query generation
  extract.py    # memory fact extraction
```

## Call shape

```python
resp = client.messages.create(
    model=ANSWER_MODEL,                     # "claude-opus-5"
    max_tokens=16000,
    thinking={"type": "adaptive"},          # NOT budget_tokens — 400 on Opus 5
    output_config={"effort": "high"},       # "xhigh" for synthesis questions
    system=[{"type": "text", "text": ANSWER_SYSTEM_PROMPT,
             "cache_control": {"type": "ephemeral"}}],
    messages=[...],
    betas=["server-side-fallback-2026-07-01"],
    fallbacks="default",
)
```

Rules, all of which are 400s or silent quality losses if broken:

- **`thinking={"type": "adaptive"}`** — `budget_tokens` is removed on Opus 5.
- **No assistant prefill** — also a 400. Control output shape via the system prompt or `output_config.format`.
- **Stream every user-facing call** (`client.messages.stream()` + `get_final_message()`). Large `max_tokens` on a non-streaming request hits HTTP timeouts.
- **Check `stop_reason == "refusal"`** on every response before reading content, and surface it. `stop_details` is populated only in that case.
- **Model IDs only from `models.py`.** No literals at call sites, no date suffixes.

## Prompt cache layout

Render order is `tools` → `system` → `messages`. Ours:

```
[system: ANSWER_SYSTEM_PROMPT]  ← cache_control breakpoint (stable, never interpolated)
[messages: long-term memory block]
[messages: retrieved documents + question]   ← volatile, after the last breakpoint
```

**Never interpolate anything per-request into the system prompt** — not a date, not a user id, not a filter description. One variable byte invalidates the whole prefix and the cost goes up ~35% with no visible error.

Verify with `usage.cache_read_input_tokens`, exported as `ferret_cache_read_tokens`. A persistent zero means something volatile drifted into the prefix; that's a bug, not a tuning issue.

## Citations

Each chunk is its own `document` block with `citations: {"enabled": True}` (see `documents.py`). The API returns `citations[].document_index` on cited text blocks; `citations.py` maps that index back to our chunk and its `locator` to build a deep link.

**Citations are API-guaranteed, not model-generated.** Never ask the model to emit `[1]` markers, and never regex citations out of prose. The whole anti-hallucination property of this system rests on that distinction.

## Extending

**New prompt:** a named constant in `prompts/`. Keep it stable-prefix-first if it will be cached. Prompt changes require `python -m eval.run_eval --gate` with numbers in the PR.

**New model call:** add a function to `client.py`. If you need a different model, add a constant to `models.py` with a comment on why.

## Gotchas

- Tool input JSON escaping varies on current models — always `json.loads()`, never string-match serialized input.
- `max_tokens` is a hard cap the model doesn't see; truncation looks like a confident answer that stops mid-sentence. 16000 for non-streaming, higher when streaming.
- Effort is inside `output_config`, not top-level. A misplaced `effort` is ignored rather than rejected.
