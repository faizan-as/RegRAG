"""Provider-neutral streaming event helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel, ConfigDict

StreamEventType = Literal["token", "final", "error"]


class StreamEvent(BaseModel):
    """A provider-neutral stream event for future SSE integration."""

    model_config = ConfigDict(extra="forbid")
    event: StreamEventType
    data: str
    committed: bool = False


async def token_events(tokens: AsyncIterator[str]) -> AsyncIterator[StreamEvent]:
    """Yield non-authoritative preview token events."""
    async for token in tokens:
        yield StreamEvent(event="token", data=token, committed=False)


async def final_event(message: str) -> AsyncIterator[StreamEvent]:
    """Yield the authoritative committed final event."""
    yield StreamEvent(event="final", data=message, committed=True)


async def error_event(message: str) -> AsyncIterator[StreamEvent]:
    """Yield a stream error event."""
    yield StreamEvent(event="error", data=message, committed=True)