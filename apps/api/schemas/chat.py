"""Chat request/response and SSE stream event schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.answer import Answer
from apps.api.schemas.common import TransparencyMetadata


class ChatResponse(BaseModel):
    """Non-streaming chat response with transparency metadata."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(description="Server-owned chat session identifier.")
    turn_id: str = Field(description="Durable final turn identifier.")
    answer: Answer = Field(description="Citation-first answer or refusal.")
    transparency: TransparencyMetadata = Field(description="Node/tool execution transparency.")


ChatStreamEventName = Literal["started", "node", "committed", "refused", "error", "done"]


class ChatStreamEvent(BaseModel):
    """A single SSE lifecycle event for streaming chat.

    ``token`` events are intentionally not modeled here: the current LangGraph
    workflow only streams at node boundaries, not token-by-token, so ``node``
    events are the finest-grained preview available until Phase 4 wires
    ``LLMClient.stream`` into ``generate_answer``.
    """

    model_config = ConfigDict(extra="forbid")

    event: ChatStreamEventName
    data: dict[str, Any] = Field(default_factory=dict)
