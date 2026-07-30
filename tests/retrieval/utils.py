"""Shared retrieval test fixtures."""

from __future__ import annotations

from apps.api.schemas.chunks import Chunk, ChunkType
from apps.api.schemas.search import RetrievalSource
from src.retrieval.models import RetrievalCandidate


def candidate(
    chunk_id: str,
    source: RetrievalSource,
    *,
    score: float = 1.0,
    text: str = "Evidence text for retrieval.",
    dense_score: float | None = None,
    keyword_score: float | None = None,
    rrf_score: float | None = None,
    rerank_score: float | None = None,
    rank: int | None = None,
    dense_rank: int | None = None,
    keyword_rank: int | None = None,
    reranker_failed: bool = False,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk=Chunk(
            chunk_id=chunk_id,
            document_id="example-guidance",
            chunk_type=ChunkType.CHILD,
            parent_chunk_id="example-guidance:a:0",
            text=text,
            version_hash="a" * 64,
            source_url="https://www.fda.gov/media/example/download",
            section_id="i-introduction",
            section_title="I. INTRODUCTION",
            page_number=3,
        ),
        source=source,
        score=score,
        dense_score=dense_score,
        keyword_score=keyword_score,
        rrf_score=rrf_score,
        rerank_score=rerank_score,
        rank=rank,
        dense_rank=dense_rank,
        keyword_rank=keyword_rank,
        reranker_failed=reranker_failed,
        evidence_payload={
            "slug": "example-guidance",
            "doc_title": "Example Guidance",
            "version_hash": "a" * 64,
            "status": "Final",
            "source_url": "https://www.fda.gov/media/example/download",
            "section_id": "i-introduction",
            "section_title": "I. INTRODUCTION",
            "page": 3,
        },
    )