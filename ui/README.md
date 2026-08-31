# ui — Streamlit front end

Chat, sources panel, memory panel, admin tab. **This layer talks to `app/api` over HTTP and nothing else** — no database connection, no LLM calls, no import from `app/`.

Spec: [SPEC.md §12](../../SPEC.md).

## Layout

```
app.py           # entry point, auth guard, page routing
client.py        # typed HTTP/SSE client for app/api
pages/
  chat.py        # message list, input, filters
  memory.py      # "What Ferret knows about me"
  admin.py       # sources, reindex, upload (role-gated)
components/
  citations.py   # inline [n] markers, hover snippet, click → document panel
  sources.py     # the right-hand panel with rerank scores
  document.py    # PDF page / web anchor viewer
state.py         # session_state keys in one place
```

## Boundary

The API is the only dependency. This is what makes the Streamlit→Next.js swap in [SPEC.md §5](../../SPEC.md) a bounded piece of work rather than a rewrite. **A single `import app.retrieval` here destroys that property** — if you need data the UI can't get, add an endpoint.

## SSE handling

Events arrive in a fixed order (see `app/api/README.md`). The client:

1. shows a status line on `status`,
2. **renders the sources panel on `sources`, before any token** — the panel filling first is what makes the wait feel short,
3. appends on `token`,
4. attaches markers on `citation`,
5. stores `run_id` from `done` for the feedback buttons.

**Unknown event types are ignored, not errors.** That keeps the UI forward-compatible with API additions — and it also means a mismatch fails silently, which is why UI and API event changes ship in the same PR.

An `error` event must render as a message in the thread, not a toast that disappears. Users need to be able to point at what went wrong.

## Invariants

- Never render an answer without its citation markers. An uncited answer looks identical to a cited one at a glance, and that is precisely the confusion this product exists to prevent.
- `groundedness_violation` on a response renders a visible warning band on the affected passage.
- The admin tab is hidden *and* the endpoints are role-gated server-side. Hiding alone is not authorization.
- The empty state shows 4 example questions. New users do not know what the corpus contains; a blank box gets abandoned.

## Gotchas

- **Streamlit reruns the entire script on every interaction.** Anything expensive goes behind `@st.cache_resource` (the HTTP client) or `@st.cache_data` (source lists). A plain module-level client is recreated constantly.
- Streaming into `st.write_stream` is fine; manually appending to `session_state` inside the stream loop and rerunning per token is not — it will melt.
- Session state keys are stringly-typed and easy to typo into a silent bug. Declare them all in `state.py` and reference the constants.
- The auth token needs refreshing on long-lived sessions; a 401 mid-stream should redirect to login, not render as an error bubble.
