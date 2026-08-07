"""Tests for the unified hybrid retrieval client."""

from __future__ import annotations

import pytest

from apps.api.schemas.search import RetrievalSource
from src.retrieval.client import RetrievalError, hybrid_search
from src.retrieval.models import RetrievalBackendStatus
from tests.retrieval.utils import candidate


async def test_hybrid_search_runs_injected_flow() -> None:
    model = _FakeEmbeddingModel()

    async def dense_searcher(*args, **kwargs):
        return [candidate("dense", RetrievalSource.DENSE, score=0.8, dense_score=0.8)]

    def keyword_searcher(*args, **kwargs):
        return [candidate("keyword", RetrievalSource.KEYWORD, score=7.0, keyword_score=7.0)]

    def reranker(query_text, candidates, **kwargs):
        del query_text, kwargs
        return [item.with_updates(source=RetrievalSource.RERANKED, score=1.0, rerank_score=1.0, rank=index) for index, item in enumerate(candidates, start=1)]

    result = await hybrid_search(
        "query",
        session=object(),
        opensearch_client=object(),
        embedding_model=model,
        dense_searcher=dense_searcher,
        keyword_searcher=keyword_searcher,
        reranker=reranker,
    )

    assert [item.chunk_id for item in result.candidates] == ["dense", "keyword"]
    assert len(result.search_results) == 2
    assert len(result.evidence_cards) == 2
    assert result.dense_error is None
    assert result.keyword_error is None


async def test_hybrid_search_keyword_only_fallback_still_reranks() -> None:
    async def failing_dense(*args, **kwargs):
        raise RuntimeError("dense down")

    def keyword_searcher(*args, **kwargs):
        return [candidate("keyword", RetrievalSource.KEYWORD, score=7.0, keyword_score=7.0)]

    def reranker(query_text, candidates, **kwargs):
        del query_text, kwargs
        return [candidates[0].with_updates(source=RetrievalSource.RERANKED, score=2.0, rerank_score=2.0, rank=1)]

    result = await hybrid_search(
        "query",
        session=object(),
        opensearch_client=object(),
        embedding_model=_FakeEmbeddingModel(),
        dense_searcher=failing_dense,
        keyword_searcher=keyword_searcher,
        reranker=reranker,
    )

    assert result.dense_error == "dense_unavailable"
    assert result.dense_status == RetrievalBackendStatus.FAILED
    assert result.candidates[0].rerank_score == 2.0
    assert result.evidence_cards[0].confidence > 0.0


async def test_hybrid_search_reranker_failure_uses_zero_confidence_fallback() -> None:
    async def dense_searcher(*args, **kwargs):
        return [candidate("dense", RetrievalSource.DENSE, score=0.8, dense_score=0.8)]

    def keyword_searcher(*args, **kwargs):
        return []

    def failing_reranker(*args, **kwargs):
        raise RuntimeError("reranker down")

    result = await hybrid_search(
        "query",
        session=object(),
        opensearch_client=object(),
        embedding_model=_FakeEmbeddingModel(),
        dense_searcher=dense_searcher,
        keyword_searcher=keyword_searcher,
        reranker=failing_reranker,
    )

    assert result.reranker_error == "reranker_unavailable"
    assert result.reranker_status == RetrievalBackendStatus.FAILED
    assert result.candidates[0].reranker_failed is True
    assert result.evidence_cards[0].confidence == 0.0


async def test_hybrid_search_raises_when_both_retrievers_fail() -> None:
    async def failing_dense(*args, **kwargs):
        raise RuntimeError("dense down")

    def failing_keyword(*args, **kwargs):
        raise RuntimeError("keyword down")

    with pytest.raises(RetrievalError, match="All configured retrieval backends") as exc_info:
        await hybrid_search(
            "query",
            session=object(),
            opensearch_client=object(),
            embedding_model=_FakeEmbeddingModel(),
            dense_searcher=failing_dense,
            keyword_searcher=failing_keyword,
        )
    assert exc_info.value.diagnostic_codes == ["dense_unavailable", "keyword_unavailable"]


async def test_hybrid_search_returns_successful_empty_result() -> None:
    """No matches are a successful empty result, not a dependency outage."""

    async def empty_dense(*args, **kwargs):
        return []

    def empty_keyword(*args, **kwargs):
        return []

    result = await hybrid_search(
        "query",
        session=object(),
        opensearch_client=object(),
        embedding_model=_FakeEmbeddingModel(),
        dense_searcher=empty_dense,
        keyword_searcher=empty_keyword,
    )

    assert result.candidates == []
    assert result.dense_status == RetrievalBackendStatus.EMPTY
    assert result.keyword_status == RetrievalBackendStatus.EMPTY
    assert result.reranker_status == RetrievalBackendStatus.SKIPPED


class _FakeEmbeddingModel:
    def encode(self, sentences, *, normalize_embeddings=True):
        del sentences, normalize_embeddings
        return [[0.1] * 1024]