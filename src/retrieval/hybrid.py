"""Hybrid retrieval helpers, including Reciprocal Rank Fusion."""

from __future__ import annotations

from collections.abc import Sequence

from apps.api.schemas.search import RetrievalSource
from src.retrieval.models import RetrievalCandidate


def reciprocal_rank_fusion(
    dense_results: Sequence[RetrievalCandidate],
    keyword_results: Sequence[RetrievalCandidate],
    *,
    rrf_k: int = 60,
    top_k: int,
) -> list[RetrievalCandidate]:
    """Fuse dense and keyword candidates with Reciprocal Rank Fusion."""
    if rrf_k <= 0:
        raise ValueError("rrf_k must be greater than 0")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    merged: dict[str, RetrievalCandidate] = {}
    scores: dict[str, float] = {}

    _merge_source(merged, scores, dense_results, rrf_k=rrf_k, source=RetrievalSource.DENSE)
    _merge_source(merged, scores, keyword_results, rrf_k=rrf_k, source=RetrievalSource.KEYWORD)

    fused = [
        candidate.with_updates(
            source=RetrievalSource.FUSED,
            score=scores[candidate.chunk_id],
            rrf_score=scores[candidate.chunk_id],
        )
        for candidate in merged.values()
    ]
    fused.sort(key=lambda candidate: (-candidate.rrf_score, _best_rank(candidate), candidate.chunk_id))
    return [candidate.with_updates(rank=rank) for rank, candidate in enumerate(fused[:top_k], start=1)]


def _merge_source(
    merged: dict[str, RetrievalCandidate],
    scores: dict[str, float],
    candidates: Sequence[RetrievalCandidate],
    *,
    rrf_k: int,
    source: RetrievalSource,
) -> None:
    for fallback_rank, candidate in enumerate(candidates, start=1):
        rank = candidate.rank or fallback_rank
        chunk_id = candidate.chunk_id
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (rrf_k + rank))
        existing = merged.get(chunk_id)
        if existing is None:
            merged[chunk_id] = candidate
            continue
        updates = {}
        if source == RetrievalSource.DENSE:
            updates["dense_score"] = candidate.dense_score or candidate.score
            updates["dense_rank"] = candidate.dense_rank or rank
        if source == RetrievalSource.KEYWORD:
            updates["keyword_score"] = candidate.keyword_score or candidate.score
            updates["keyword_rank"] = candidate.keyword_rank or rank
        if not existing.evidence_payload and candidate.evidence_payload:
            updates["evidence_payload"] = candidate.evidence_payload
        merged[chunk_id] = existing.with_updates(**updates)


def _best_rank(candidate: RetrievalCandidate) -> int:
    ranks = [rank for rank in (candidate.dense_rank, candidate.keyword_rank, candidate.rank) if rank]
    return min(ranks) if ranks else 999_999