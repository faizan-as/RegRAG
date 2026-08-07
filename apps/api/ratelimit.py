"""MVP rate limiting for user-facing API routes.

The docker-compose stack has no Redis or other shared cache, so this
implements a single-process in-memory sliding-window limiter. This is only
correct behind a single API worker; a multi-worker deployment must replace
this with a shared backend (e.g. a Postgres-backed counter table) before
horizontal scaling, per the Phase 5 plan's documented decision.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import lru_cache

from fastapi import Depends

from apps.api.errors import RateLimitError
from apps.api.security import AuthenticatedUser, get_current_user
from apps.api.settings import get_settings


class InMemoryRateLimiter:
    """A single-process sliding-window rate limiter keyed by caller id."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        """Raise ``RateLimitError`` when the caller has exceeded the window budget."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        async with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= self.max_requests:
                raise RateLimitError("Rate limit exceeded. Please try again later.")
            hits.append(now)


@lru_cache
def get_named_rate_limiter(name: str, max_requests: int) -> InMemoryRateLimiter:
    """Return a process-wide limiter for one named route budget."""
    del name
    return InMemoryRateLimiter(max_requests=max_requests)


async def enforce_rate_limit(user: AuthenticatedUser = Depends(get_current_user)) -> None:
    """Enforce the legacy general per-user rate limit."""
    settings = get_settings()
    limiter = get_named_rate_limiter("general", settings.rate_limit_per_minute)
    await limiter.check(user.user_id)


def _route_limit(name: str, setting_name: str) -> Callable[..., Awaitable[None]]:
    async def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> None:
        settings = get_settings()
        limiter = get_named_rate_limiter(name, getattr(settings, setting_name))
        await limiter.check(user.user_id)

    return dependency


enforce_chat_rate_limit = _route_limit("chat", "chat_rate_limit_per_minute")
enforce_search_rate_limit = _route_limit("search", "search_rate_limit_per_minute")
enforce_summary_rate_limit = _route_limit("summary", "summary_rate_limit_per_minute")
enforce_export_rate_limit = _route_limit("export", "export_rate_limit_per_minute")
enforce_document_rate_limit = _route_limit("document", "document_rate_limit_per_minute")


class ActiveStreamLimiter:
    """Single-process concurrent stream limiter keyed by authenticated user."""

    def __init__(self) -> None:
        self._active: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(self, key: str, maximum: int) -> None:
        async with self._lock:
            if self._active[key] >= maximum:
                raise RateLimitError("Too many active chat streams.")
            self._active[key] += 1

    async def release(self, key: str) -> None:
        async with self._lock:
            self._active[key] = max(0, self._active[key] - 1)
            if self._active[key] == 0:
                self._active.pop(key, None)


@lru_cache
def get_active_stream_limiter() -> ActiveStreamLimiter:
    """Return the process-wide active stream limiter."""
    return ActiveStreamLimiter()


async def acquire_stream_lease(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AsyncIterator[None]:
    """Hold one per-user stream slot for the response dependency lifetime."""
    limiter = get_active_stream_limiter()
    await limiter.acquire(user.user_id, get_settings().max_active_streams_per_user)
    try:
        yield
    finally:
        await limiter.release(user.user_id)
