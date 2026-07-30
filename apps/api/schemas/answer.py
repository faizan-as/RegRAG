"""Answer request/response models for the citation-first chat contract."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.evidence import EvidenceCard


class AnswerRequest(BaseModel):
    """A user query submitted to the agent workflow."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="Natural-language regulatory question.")
    session_id: str | None = Field(
        default=None, description="Conversation/session identifier for continuity."
    )
    filters: dict[str, str] = Field(
        default_factory=dict,
        description="Optional retrieval filters (e.g. status, office).",
    )


class Answer(BaseModel):
    """A generated answer with mandatory supporting evidence.

    Every answer must include at least one :class:`EvidenceCard`. When the
    workflow cannot ground its claims, ``refused`` is set and ``text`` explains
    the refusal instead of asserting an unsupported answer.
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="Generated answer text with inline citation markers.")
    evidence: list[EvidenceCard] = Field(
        description="Evidence Cards backing each cited claim."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall answer confidence from guardrails."
    )
    refused: bool = Field(
        default=False,
        description="True when the workflow refused due to insufficient grounding.",
    )
    refusal_reason: str | None = Field(
        default=None, description="Explanation when the answer was refused."
    )
    session_id: str | None = Field(default=None, description="Owning session id.")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Answer generation timestamp.",
    )
