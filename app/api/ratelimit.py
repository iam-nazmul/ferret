"""Per-user rate limiting.

Applied before the graph is invoked — a rejected request must not cost an LLM call.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.config import settings


class RateLimiter:
    """In-process limiter. Redis-backed is the multi-replica upgrade path."""

    def __init__(self, per_minute: int | None = None, concurrent: int | None = None) -> None:
        self._per_minute = per_minute or settings.rate_limit_per_minute
        self._concurrent = concurrent or settings.rate_limit_concurrent
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._active: dict[str, int] = defaultdict(int)

    def check(self, user_id: str) -> None:
        now = time.monotonic()
        window = self._calls[user_id]
        while window and now - window[0] > 60:
            window.popleft()

        if len(window) >= self._per_minute:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"rate limit: {self._per_minute} questions per minute",
            )
        if self._active[user_id] >= self._concurrent:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"rate limit: {self._concurrent} concurrent questions",
            )
        window.append(now)

    def acquire(self, user_id: str) -> None:
        self._active[user_id] += 1

    def release(self, user_id: str) -> None:
        self._active[user_id] = max(0, self._active[user_id] - 1)


limiter = RateLimiter()
