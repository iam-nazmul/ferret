"""SSE event serialization.

Event order is fixed and the UI depends on it:
  status -> sources -> token* -> citation* -> done | error

`sources` is emitted BEFORE the first token so the panel fills while the answer streams.
Any failure becomes a terminal `error` event — the stream must never just stop.
"""

import json
from typing import Any

HEARTBEAT = ": ping\n\n"


def event(name: str, data: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def status(stage: str) -> str:
    return event("status", {"stage": stage})


def sources(items: list[dict]) -> str:
    return event("sources", {"sources": items})


def token(text: str) -> str:
    return event("token", {"text": text})


def citation(item: dict) -> str:
    return event("citation", item)


def done(run_id: str, usage: dict, latency_ms: int, groundedness_violation: bool = False) -> str:
    return event(
        "done",
        {
            "run_id": run_id,
            "usage": usage,
            "latency_ms": latency_ms,
            "groundedness_violation": groundedness_violation,
        },
    )


def error(message: str, code: str = "internal_error") -> str:
    return event("error", {"message": message, "code": code})
