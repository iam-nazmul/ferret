# Reference — Claude API as Ferret uses it

Verified against Anthropic docs, 2026-08. **Several of these differ from patterns you may recall from training data.** When in doubt, this file wins over recollection; the live docs win over this file.

All calls go through `app/llm/client.py`. Nothing else imports `anthropic`.

## Models

| Role | ID | Price in/out per MTok |
|---|---|---|
| Answers, offline judge | `claude-opus-5` | $5 / $25 |
| Grading, extraction, online judge | `claude-haiku-4-5` | $1 / $5 |
| Cost-reduction fallback (last resort) | `claude-sonnet-5` | $2 / $10 |

Exact strings, no date suffixes appended. Referenced through constants in `app/llm/models.py`.

## Request shape

```python
resp = client.messages.create(
    model=ANSWER_MODEL,
    max_tokens=16000,                       # 64000 when streaming
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},       # low | medium | high | xhigh | max
    system=[{"type": "text", "text": ANSWER_SYSTEM_PROMPT,
             "cache_control": {"type": "ephemeral"}}],
    messages=[...],
    betas=["server-side-fallback-2026-07-01"],
    fallbacks="default",
)
```

### Things that return 400

- **`thinking={"type": "enabled", "budget_tokens": N}`** — `budget_tokens` is removed on Opus 5. Use `{"type": "adaptive"}` and control depth with `output_config.effort`.
- **Assistant prefill** (a trailing assistant message to steer format) — removed on Opus 5 / Sonnet 5 / the 4.6+ family. Use the system prompt or `output_config.format`.
- **`temperature` / `top_p` / `top_k`** — removed on these models.

### Things that fail quietly

- **`effort` at the top level** instead of inside `output_config` — ignored, not rejected.
- **`max_tokens` too low** — truncates mid-sentence and reads as a confident partial answer.
- **Non-streaming with large `max_tokens`** — hits HTTP timeouts. Stream anything user-facing: `client.messages.stream()` + `.get_final_message()`.

### Refusal

`stop_reason == "refusal"` arrives as HTTP 200. Check it **before** reading `content`. `stop_details` (with `category`) is populated only in that case and is `null` for every other stop reason — always guard before accessing it.

## Citations — the core mechanism

Each retrieved chunk is its own `document` block:

```python
{
    "type": "document",
    "source": {"type": "content",
               "content": [{"type": "text", "text": chunk.text}]},
    "title": f"{doc_title} — {' > '.join(heading_path)}",
    "context": json.dumps({"uri": ..., "locator": ...}),
    "citations": {"enabled": True},
}
```

`citations` must be enabled on **all** document blocks or none.

The response splits into multiple `text` blocks; cited ones carry a `citations` array with `cited_text`, `document_index`, `document_title`, and a location whose `type` varies — `content_block_location` for the custom-content blocks we send. `document_index` maps back to our chunk list by position, and from there to the `locator` for deep linking.

**Citations are API-guaranteed, not model-generated.** Never prompt for `[1]` markers, never regex them out of prose. This is what makes hallucinated citations categorically impossible.

Incompatible with `output_config.format` — using both returns 400.

## Prompt caching

Render order: `tools` → `system` → `messages`. Prefix match — any byte change anywhere in the prefix invalidates everything after it.

Ferret's layout: stable system prompt with the breakpoint → memory block → retrieved documents + question.

Max 4 breakpoints per request. Minimum cacheable prefix is model-dependent (512–4096 tokens); shorter prefixes silently don't cache.

**Verify with `usage.cache_read_input_tokens`.** Persistent zero across repeated requests means a silent invalidator — a timestamp, an unsorted dict, a varying tool list — drifted into the prefix.

## Also worth knowing

- Parse tool inputs with `json.loads()`; JSON string escaping varies across current models, so raw string matching on serialized input breaks.
- `inference_geo="us"` is a **top-level** parameter, not `extra_body`.
- Catch a specific-to-general exception chain (`NotFoundError` → `RateLimitError` → `APIStatusError` → `APIConnectionError`), not one broad class — retryable and non-retryable failures need different handling.
- Batch API is 50% cost for non-latency-sensitive work; results return in any order, key by `custom_id`.
