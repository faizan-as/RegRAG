"""Retrieval result models spanning dense, keyword, fused, and reranked hits."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.chunks import Chunk
from apps.api.schemas.common import TransparencyMetadata
from apps.api.schemas.evidence import EvidenceCard


class RetrievalSource(str, Enum):
    """Origin of a retrieval candidate."""

    DENSE = "dense"
    KEYWORD = "keyword"
    FUSED = "fused"
    RERANKED = "reranked"


class SearchResult(BaseModel):
    """A single retrieval candidate with ranking scores."""

    model_config = ConfigDict(extra="forbid")

    chunk: Chunk = Field(description="The retrieved chunk.")
    source: RetrievalSource = Field(description="Retrieval stage that produced the hit.")
    score: float = Field(description="Score from the producing retrieval stage.")
    dense_score: float | None = Field(default=None, description="Dense (vector) similarity score.")
    keyword_score: float | None = Field(default=None, description="BM25 keyword score.")
    rrf_score: float | None = Field(default=None, description="Reciprocal rank fusion score.")
    rerank_score: float | None = Field(default=None, description="Cross-encoder reranker score.")
    rank: int | None = Field(default=None, ge=0, description="Position in the ranked result list.")


class SearchRequest(BaseModel):
    """A hybrid retrieval request with optional metadata filters."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="Natural-language search query.")
    filters: dict[str, str] = Field(
        default_factory=dict, description="Optional retrieval filters (e.g. status, center)."
    )
    top_k: int | None = Field(
        default=None, ge=1, le=100, description="Retrieval candidate count override."
    )
    rerank_top_k: int | None = Field(
        default=None, ge=1, le=50, description="Reranked result count override."
    )


class SearchResponse(BaseModel):
    """Retrieved/reranked evidence for a search query. Does not generate an answer."""

    model_config = ConfigDict(extra="forbid")

    results: list[SearchResult] = Field(default_factory=list)
    evidence: list[EvidenceCard] = Field(default_factory=list)
    transparency: TransparencyMetadata
