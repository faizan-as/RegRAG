"""Tests for reranking retrieval candidates."""

from __future__ import annotations

import pytest

from apps.api.schemas.search import RetrievalSource
from src.retrieval.reranker import rerank_results
from tests.retrieval.utils import candidate


def test_rerank_results_scores_batches_and_truncates() -> None:
    model = _FakeReranker(scores=[0.1, 1.5, 0.5])
    candidates = [candidate("a", RetrievalSource.FUSED, text="A"), candidate("b", RetrievalSource.FUSED, text="B"), candidate("c", RetrievalSource.FUSED, text="C")]

    reranked = rerank_results("query", candidates, model=model, top_k=2, batch_size=2)

    assert [item.chunk_id for item in reranked] == ["b", "c"]
    assert reranked[0].source == RetrievalSource.RERANKED
    assert reranked[0].rerank_score == 1.5
    assert reranked[0].rank == 1
    assert model.calls == [[("query", "A"), ("query", "B")], [("query", "C")]]


def test_rerank_results_handles_empty_candidates() -> None:
    assert rerank_results("query", [], model=_FakeReranker(scores=[]), top_k=5) == []


def test_rerank_results_rejects_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="top_k"):
        rerank_results("query", [candidate("a", RetrievalSource.FUSED)], model=_FakeReranker(scores=[]), top_k=0)
    with pytest.raises(ValueError, match="batch_size"):
        rerank_results("query", [candidate("a", RetrievalSource.FUSED)], model=_FakeReranker(scores=[]), top_k=1, batch_size=0)


class _FakeReranker:
    def __init__(self, *, scores: list[float]) -> None:
        self.scores = scores
        self.calls = []

    def predict(self, pairs):
        pairs = list(pairs)
        self.calls.append(pairs)
        start = sum(len(call) for call in self.calls[:-1])
        return self.scores[start : start + len(pairs)]