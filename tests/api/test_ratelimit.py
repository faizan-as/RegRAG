"""Tests for route and active-stream rate limiting."""

from __future__ import annotations

import pytest

from apps.api.errors import RateLimitError
from apps.api.ratelimit import ActiveStreamLimiter, InMemoryRateLimiter


async def test_sliding_window_rejects_over_budget() -> None:
    limiter = InMemoryRateLimiter(max_requests=1)
    await limiter.check("user-1")

    with pytest.raises(RateLimitError):
        await limiter.check("user-1")


async def test_stream_slot_is_reusable_after_release() -> None:
    limiter = ActiveStreamLimiter()
    await limiter.acquire("user-1", 1)
    with pytest.raises(RateLimitError):
        await limiter.acquire("user-1", 1)

    await limiter.release("user-1")
    await limiter.acquire("user-1", 1)
    await limiter.release("user-1")
