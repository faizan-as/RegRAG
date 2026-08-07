"""Evidence Card model: the citation-first contract for every answer.

An :class:`EvidenceCard` binds a generated claim to an exact FDA source
passage with the provenance required for auditability. Citation binding
fails closed: unbound claims trigger a retry or refusal upstream.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from apps.api.schemas.documents import DocumentStatus


class EvidenceCard(BaseModel):
    """A verifiable citation binding a claim to an FDA source passage."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(description="Stable answer-local citation marker, such as '[1]'.")
    document_id: str = Field(description="Stable internal FDA document identifier.")
    title: str = Field(description="FDA guidance title.")
    section_id: str | None = Field(
        default=None, description="Normalized section identifier when available."
    )
    section_title: str | None = Field(default=None, description="Human-readable section heading.")
    page_number: int | None = Field(
        default=None, ge=0, description="PDF page number for source inspection."
    )
    passage: str = Field(description="Exact quoted or cited source passage.")
    source_url: HttpUrl = Field(description="FDA source URL.")
    version_hash: str = Field(description="SHA-256 hash of the source document version.")
    document_status: DocumentStatus = Field(description="Draft, Final, or Withdrawn.")
    retrieval_score: float = Field(description="Dense/BM25/RRF retrieval score used for ranking.")
    rerank_score: float = Field(description="Cross-encoder reranker score.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Final evidence confidence used by guardrails."
    )
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of retrieval for auditability.",
    )
