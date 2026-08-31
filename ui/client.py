"""Typed HTTP/SSE client for app/api."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class StreamResult:
    answer: str = ""
    sources: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    run_id: str = ""
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    groundedness_violation: bool = False
    error: str | None = None


class FerretClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    def chat(
        self, message: str, thread_id: str | None, filters: dict | None = None
    ) -> Iterator[tuple[str, Any]]:
        """Yields (event_name, payload). Unknown event types are the caller's to ignore."""
        payload: dict[str, Any] = {"message": message, "thread_id": thread_id}
        if filters:
            payload["filters"] = filters

        with httpx.Client(timeout=120) as client, client.stream(
            "POST", f"{self._base}/v1/chat", json=payload, headers=self._headers
        ) as resp:
            if resp.status_code >= 400:
                resp.read()
                yield "error", {"message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
                return

            event_name = None
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith(":"):  # heartbeat
                    continue
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and event_name:
                    try:
                        yield event_name, json.loads(line.split(":", 1)[1].strip())
                    except json.JSONDecodeError:
                        continue

    def feedback(self, run_id: str, thread_id: str, score: int, comment: str = "") -> None:
        httpx.post(
            f"{self._base}/v1/feedback",
            json={
                "run_id": run_id,
                "thread_id": thread_id,
                "score": score,
                "comment": comment or None,
            },
            headers=self._headers,
            timeout=15,
        )

    def memories(self) -> list[dict]:
        r = httpx.get(f"{self._base}/v1/memories", headers=self._headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def delete_memory(self, memory_id: str) -> None:
        httpx.delete(f"{self._base}/v1/memories/{memory_id}", headers=self._headers, timeout=15)

    def clear_memories(self) -> int:
        r = httpx.delete(f"{self._base}/v1/memories", headers=self._headers, timeout=30)
        return r.json().get("deleted", 0)

    def sources(self) -> list[dict]:
        r = httpx.get(f"{self._base}/v1/sources", headers=self._headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def failures(self, source_id: str) -> list[dict]:
        r = httpx.get(
            f"{self._base}/v1/sources/{source_id}/failures", headers=self._headers, timeout=30
        )
        r.raise_for_status()
        return r.json()

    def reindex(self, source_id: str) -> None:
        httpx.post(
            f"{self._base}/v1/sources/{source_id}/reindex", headers=self._headers, timeout=30
        )

    def upload(self, filename: str, content: bytes, acl_groups: str, doc_type: str) -> dict:
        r = httpx.post(
            f"{self._base}/v1/documents",
            files={"file": (filename, content, "application/pdf")},
            data={"acl_groups": acl_groups, "doc_type": doc_type},
            headers=self._headers,
            timeout=300,
        )
        r.raise_for_status()
        return r.json()
