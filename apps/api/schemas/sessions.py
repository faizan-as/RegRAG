"""Server-owned chat session and turn API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.answer import Answer


class SessionCreateRequest(BaseModel):
    """Request to create a user-owned chat session."""

    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=255)


class SessionResponse(BaseModel):
    """Public chat session metadata."""

    model_config = ConfigDict(extra="forbid")
    session_id: str
    title: str | None = None
    status: str
    created_at: datetime


class SessionListResponse(BaseModel):
    """Newest-first page of chat sessions owned by the caller."""

    model_config = ConfigDict(extra="forbid")
    sessions: list[SessionResponse] = Field(default_factory=list)
    limit: int
    offset: int


class TurnResponse(BaseModel):
    """One immutable final answer or refusal in a session."""

    model_config = ConfigDict(extra="forbid")
    turn_id: str
    query: str
    answer: Answer
    created_at: datetime


class SessionHistoryResponse(BaseModel):
    """Ordered immutable turns for an authorized session."""

    model_config = ConfigDict(extra="forbid")
    session_id: str
    turns: list[TurnResponse] = Field(default_factory=list)
