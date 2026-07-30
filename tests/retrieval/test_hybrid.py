"""Tests for Reciprocal Rank Fusion."""

from __future__ import annotations

import pytest

from apps.api.schemas.search import RetrievalSource
from src.retrieval.hybrid import reciprocal_rank_fusion
from tests.retrieval.utils import candidate


def test_reciprocal_rank_fusion_deduplicates_and_scores() -> None:
    dense = [candidate("a", RetrievalSource.DENSE, score=0.9, rank=1, dense_score=0.9, dense_rank=1)]
    keyword = [
        candidate("a", RetrievalSource.KEYWORD, score=8.0, rank=2, keyword_score=8.0, keyword_rank=2),
        candidate("b", RetrievalSource.KEYWORD, score=7.0, rank=1, keyword_score=7.0, keyword_rank=1),
    ]

    fused = reciprocal_rank_fusion(dense, keyword, rrf_k=60, top_k=10)

    assert [item.chunk_id for item in fused] == ["a", "b"]
    assert fused[0].source == RetrievalSource.FUSED
    assert fused[0].rrf_score == pytest.approx((1 / 61) + (1 / 62))
    assert fused[0].dense_score == 0.9
    assert fused[0].keyword_score == 8.0
    assert fused[0].rank == 1


def test_reciprocal_rank_fusion_handles_single_source_and_limits() -> None:
    fused = reciprocal_rank_fusion(
        [],
        [candidate("b", RetrievalSource.KEYWORD, score=7.0), candidate("a", RetrievalSource.KEYWORD, score=6.0)],
        rrf_k=60,
        top_k=1,
    )

    assert [item.chunk_id for item in fused] == ["b"]


def test_reciprocal_rank_fusion_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="rrf_k"):
        reciprocal_rank_fusion([], [], rrf_k=0, top_k=1)
    with pytest.raises(ValueError, match="top_k"):
        reciprocal_rank_fusion([], [], top_k=0)