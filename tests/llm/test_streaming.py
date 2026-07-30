"""Tests for provider-neutral streaming helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from src.llm.streaming import error_event, final_event, token_events


async def _tokens() -> AsyncIterator[str]:
    yield "a"
    yield "b"


async def test_token_events_are_preview_events() -> None:
    events = [event async for event in token_events(_tokens())]

    assert [event.data for event in events] == ["a", "b"]
    assert all(event.committed is False for event in events)


async def test_final_and_error_events_are_committed() -> None:
    final = [event async for event in final_event("done")]
    error = [event async for event in error_event("bad")]

    assert final[0].event == "final"
    assert final[0].committed is True
    assert error[0].event == "error"
    assert error[0].committed is True