# Reference — LangGraph persistence

Verified against LangGraph docs, 2026-08. Used by `app/graph/` and `app/memory/`.

## Checkpointer vs. store

The distinction is the whole design, and conflating them is the main failure mode.

| | Checkpointer | Store |
|---|---|---|
| Persists | graph state snapshots for **one thread** | application data **across threads** |
| Keyed by | `thread_id` (via `config.configurable`) | a namespace tuple you choose |
| Gives you | conversation continuity, time travel, fault tolerance | user preferences, facts, shared knowledge |
| Read | automatically by the graph | explicitly, via `store.asearch` / `aget` |

```python
graph = builder.compile(checkpointer=checkpointer, store=store)
```

## Short-term: checkpointer

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
    # await checkpointer.setup()   # first run only, creates its tables
    graph = builder.compile(checkpointer=checkpointer)

await graph.ainvoke(
    {"messages": [{"role": "user", "content": "..."}]},
    {"configurable": {"thread_id": "abc"}},
)
```

`InMemorySaver` for tests. Everything in state must be JSON-serializable — a dataclass is fine, an open connection is not.

## Long-term: store with semantic search

```python
from langgraph.store.postgres.aio import AsyncPostgresStore

store = AsyncPostgresStore.from_conn_string(
    DB_URI, index={"embed": embeddings, "dims": 1024}
)

await store.aput(("memories", user_id), str(uuid4()), {"data": fact})
items = await store.asearch(("memories", user_id), query=last_message, limit=5)
memories = "\n".join(item.value["data"] for item in items)
```

`asearch` embeds and matches on the value's indexed text field, so **anything you want retrievable belongs in `data`**, not in sibling metadata keys.

There is **no ACL layer on the store.** The namespace is the only isolation. Always `("memories", user_id)` — never an org-level or shared namespace, and never document content (that would be an unauthorized second copy of the corpus outside the permission model).

## Accessing the store inside a node

```python
from langgraph.runtime import Runtime

async def generate(state: MessagesState, runtime: Runtime[Context]):
    user_id = runtime.context.user_id
    items = await runtime.store.asearch(("memories", user_id),
                                        query=state["messages"][-1].content, limit=5)
    ...
```

`Runtime` gives nodes the store and typed per-run context. Declare the context type on the builder:

```python
builder = StateGraph(MessagesState, context_schema=Context)
graph.astream_events({...}, config, version="v3", context=Context(user_id="1"))
```

## State and nodes

```python
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    ...
```

`add_messages` merges **by id** — constructing a new message with an existing id replaces rather than appends. Occasionally what you want; usually a bug.

Nodes are pure functions of state returning partial updates. Keep them that way: it's what makes per-node testing and concurrent execution safe.

## Pitfalls

- Node exceptions abort the run and lose the partial answer. Nodes calling external services should degrade and log, not raise.
- Checkpoint tables grow monotonically. A retention job is mandatory in prod.
- Conditional edges belong in the graph builder, not as branching returns buried in nodes — topology in one file is what keeps the graph readable.
- Store embedding dimensions must match retrieval's. A mismatch degrades silently rather than erroring.
