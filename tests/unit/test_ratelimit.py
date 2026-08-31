"""Rate limiting runs before the graph — a rejected request must not cost an LLM call."""

import pytest
from fastapi import HTTPException

from app.api.ratelimit import RateLimiter


def test_allows_within_budget():
    limiter = RateLimiter(per_minute=3, concurrent=2)
    for _ in range(3):
        limiter.check("u")


def test_blocks_over_per_minute_budget():
    limiter = RateLimiter(per_minute=2, concurrent=5)
    limiter.check("u")
    limiter.check("u")
    with pytest.raises(HTTPException) as exc:
        limiter.check("u")
    assert exc.value.status_code == 429


def test_blocks_over_concurrency_budget():
    limiter = RateLimiter(per_minute=100, concurrent=1)
    limiter.check("u")
    limiter.acquire("u")
    with pytest.raises(HTTPException):
        limiter.check("u")


def test_release_frees_a_slot():
    limiter = RateLimiter(per_minute=100, concurrent=1)
    limiter.acquire("u")
    limiter.release("u")
    limiter.check("u")


def test_users_are_independent():
    limiter = RateLimiter(per_minute=1, concurrent=1)
    limiter.check("alice")
    limiter.check("bob")
