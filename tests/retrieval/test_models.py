"""Tests for internal retrieval models."""

from __future__ import annotations

from apps.api.schemas.chunks import Chunk, ChunkType
from apps.api.schemas.search import RetrievalSource
from src.retrieval.models import RetrievalCandidate


def test_retrieval_candidate_carries_evidence_payload_and_scores() -> None:
    candidate = RetrievalCandidate(
        chunk=_chunk(),
        source=RetrievalSource.DENSE,
        score=0.9,
        dense_score=0.9,
        rank=1,
        evidence_payload={"doc_title": "Example Guidance"},
    )

    assert candidate.chunk_id == "example-guidance:a:1"
    assert candidate.evidence_payload["doc_title"] == "Example Guidance"
    assert candidate.dense_score == 0.9


def test_retrieval_candidate_with_updates_returns_copy() -> None:
    candidate = RetrievalCandidate(chunk=_chunk(), source=RetrievalSource.DENSE, score=0.5)

    updated = candidate.with_updates(source=RetrievalSource.RERANKED, score=1.25)

    assert updated is not candidate
    assert updated.source == RetrievalSource.RERANKED
    assert updated.score == 1.25
    assert candidate.source == RetrievalSource.DENSE


def _chunk() -> Chunk:
    return Chunk(
        chunk_id="example-guidance:a:1",
        document_id="example-guidance",
        chunk_type=ChunkType.CHILD,
        parent_chunk_id="example-guidance:a:0",
        text="Evidence text.",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        section_title="I. INTRODUCTION",
        page_number=3,
    )