"""Typed state models for the citation-first LangGraph workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.answer import Answer
from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.search import SearchResult
from src.retrieval.filters import RetrievalFilters
from src.retrieval.models import HybridSearchResult, RetrievalCandidate

Intent = Literal["question", "summary", "requirements", "changes", "unsupported"]
RetrievalRoute = Literal["hybrid", "metadata_constrained"]
NodeStatus = Literal["success", "failed", "skipped"]


class QueryUnderstanding(BaseModel):
    """Normalized query understanding produced before retrieval."""

    model_config = ConfigDict(extra="forbid")

    rewritten_query: str = Field(description="Search-optimized rewrite of the user query.")
    intent: Intent = Field(default="question", description="Classified user intent.")
    entities: dict[str, list[str]] = Field(
        default_factory=dict, description="FDA-specific entities extracted from the query."
    )


class ExecutionTraceEntry(BaseModel):
    """Trace metadata for one workflow node execution."""

    model_config = ConfigDict(extra="forbid")

    node: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: NodeStatus = "success"
    error_type: str | None = None
    error_message: str | None = None
    provider: str | None = None
    evidence_count: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    retry_count: int | None = Field(default=None, ge=0)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CitationBindingResult(BaseModel):
    """Result of fail-closed citation binding."""

    model_config = ConfigDict(extra="forbid")
    success: bool
    bound_cards: list[EvidenceCard] = Field(default_factory=list)
    cited_ids: list[str] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class RefusalMetadata(BaseModel):
    """Structured refusal metadata carried through the workflow."""

    model_config = ConfigDict(extra="forbid")
    reason: str
    message: str


class AgentState(TypedDict, total=False):
    """LangGraph-compatible state for the Phase 4 agent workflow."""

    query: str
    session_id: str | None
    raw_filters: dict[str, str]
    filters: RetrievalFilters | None
    ignored_filter_keys: list[str]
    understanding: QueryUnderstanding
    rewritten_query: str
    intent: Intent
    entities: dict[str, list[str]]
    retrieval_route: RetrievalRoute
    hybrid_result: HybridSearchResult
    candidates: list[RetrievalCandidate]
    search_results: list[SearchResult]
    evidence_cards: list[EvidenceCard]
    retrieval_diagnostics: dict[str, Any]
    generated_answer: str
    prompt_version: str
    llm_provider: str
    token_usage: dict[str, Any]
    confidence: float
    confidence_sufficient: bool
    citation_binding: CitationBindingResult
    bound_evidence: list[EvidenceCard]
    faithfulness_passed: bool
    faithfulness_reason: str | None
    retry_count: int
    max_retries: int
    refused: bool
    refusal: RefusalMetadata
    answer: Answer
    execution_trace: list[ExecutionTraceEntry]
    provider_fallback_trace: list[str]
    retrieval_errors: list[str]
    guardrail_errors: list[str]


def initial_agent_state(
    query: str,
    *,
    session_id: str | None = None,
    filters: dict[str, str] | None = None,
    max_retries: int = 1,
) -> AgentState:
    """Create an initialized workflow state for a user query."""
    return AgentState(
        query=query,
        session_id=session_id,
        raw_filters=filters or {},
        ignored_filter_keys=[],
        retry_count=0,
        max_retries=max_retries,
        refused=False,
        confidence=0.0,
        confidence_sufficient=False,
        execution_trace=[],
        provider_fallback_trace=[],
        retrieval_errors=[],
        guardrail_errors=[],
    )


def append_trace(state: AgentState, entry: ExecutionTraceEntry) -> list[ExecutionTraceEntry]:
    """Return the existing trace with one appended entry."""
    return [*state.get("execution_trace", []), entry]