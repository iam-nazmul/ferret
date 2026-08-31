# app/memory — short-term and long-term memory

Two tiers, following LangGraph's checkpointer/store split. **Conversation state is the checkpointer; facts about a user are the store.** Conflating them is the main failure mode here.

Spec: [SPEC.md §10](../../SPEC.md).

## Layout

```
checkpointer.py  # AsyncPostgresSaver setup, thread summarization
store.py         # AsyncPostgresStore with semantic search
extraction.py    # end-of-turn candidate fact extraction + dedupe
retention.py     # thread expiry job (90d), memory export/erasure
```

## The split

| | Checkpointer | Store |
|---|---|---|
| Keyed by | `thread_id` | `("memories", user_id)` |
| Holds | full message history + graph state | discrete facts about the user |
| Lifetime | 90 days | until the user deletes it |
| Read | automatically by LangGraph | explicitly via `asearch` in the graph |

```python
store = AsyncPostgresStore.from_conn_string(
    DB_URI, index={"embed": embeddings, "dims": 1024}
)
mems = await runtime.store.asearch(("memories", user_id),
                                   query=latest_user_msg, limit=5)
await runtime.store.aput(("memories", user_id), str(uuid4()),
                         {"data": fact, "source_thread": thread_id})
```

## Extraction policy

**Store:** role and team, active projects/vendors, format preferences, recurring topics.

**Never store:** document content (that's what retrieval is for — duplicating it here creates a second, stale, unauthorized copy of the corpus that bypasses ACL), or personal/sensitive details the user did not state directly.

That first exclusion is a security property, not a style preference: the store is keyed by user with no ACL join, so anything from a document that lands in it has escaped the permission model.

Extraction runs once per turn on Haiku 4.5. Candidates are checked against the same namespace by semantic similarity — near-duplicates merge, others insert.

## Invariants

- Namespace is always `("memories", user_id)`. Never a shared or org-level namespace — there is no ACL layer on the store.
- Thread summarization triggers past 40 messages: the older span collapses into one system note. Without it, context cost grows without bound on long threads.
- `retention.py` must run in prod. Checkpoint tables grow monotonically otherwise.
- Deletion is real deletion, not a tombstone — this is the GDPR erasure path.

## Extending

**Changing what gets extracted:** edit `prompts/extract.py` in `app/llm/`, not here. This module orchestrates; the prompt lives with the other prompts.

**Adding a memory type:** keep the value shape `{"data": str, ...metadata}`. `asearch` embeds `data`, so anything you want retrievable belongs in that field, not in metadata.

## Gotchas

- Store embeddings must be the same 1024d config as retrieval. A mismatch degrades silently.
- `asearch` with an empty query returns nothing useful — guard the first turn of a thread.
- Deleting a thread does not delete extracted memories, by design. The UI must say so, or users will think clearing chat history cleared their profile.
