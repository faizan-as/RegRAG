"""Internal retrieval models used between dense, keyword, fusion, and reranking."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.chunks import Chunk
from apps.api.schemas.search import SearchResult
from apps.api.schemas.search import RetrievalSource


@dataclass(frozen=True)
class RetrievalCandidate:
    """A retrieval candidate carrying internal payloads that API schemas forbid."""

    chunk: Chunk
    source: RetrievalSource
    score: float
    evidence_payload: dict[str, Any] = field(default_factory=dict)
    dense_score: float | None = None
    keyword_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    rank: int | None = None
    dense_rank: int | None = None
    keyword_rank: int | None = None
    reranker_failed: bool = False

    @property
    def chunk_id(self) -> str:
        """Return the stable chunk identifier used for deduplication."""
        return self.chunk.chunk_id

    def with_updates(self, **updates: Any) -> RetrievalCandidate:
        """Return a copy with updated fields."""
        return replace(self, **updates)


class RetrievalBackendStatus(str, Enum):
    """Safe outcome status for one retrieval backend or reranking stage."""

    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class HybridSearchResult:
    """Final hybrid retrieval result with API-ready outputs and diagnostics."""

    query_text: str
    candidates: list[RetrievalCandidate]
    search_results: list[SearchResult]
    evidence_cards: list[EvidenceCard]
    dense_status: RetrievalBackendStatus = RetrievalBackendStatus.SUCCESS
    keyword_status: RetrievalBackendStatus = RetrievalBackendStatus.SUCCESS
    reranker_status: RetrievalBackendStatus = RetrievalBackendStatus.SUCCESS
    dense_error: str | None = None
    keyword_error: str | None = None
    reranker_error: str | None = None