"""Unified hybrid retrieval client."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from apps.api.settings import get_settings
from src.retrieval.filters import RetrievalFilters
from src.retrieval.formatting import candidates_to_evidence_cards, candidates_to_search_results
from src.retrieval.hybrid import reciprocal_rank_fusion
from src.retrieval.models import HybridSearchResult, RetrievalCandidate
from src.retrieval.opensearch_client import search_keyword_chunks
from src.retrieval.pgvector_client import search_dense_chunks
from src.retrieval.query_embedding import embed_query
from src.retrieval.reranker import rerank_results


class RetrievalError(RuntimeError):
    """Raised when hybrid retrieval cannot produce candidates."""


DenseSearcher = Callable[..., Awaitable[list[RetrievalCandidate]]]
KeywordSearcher = Callable[..., list[RetrievalCandidate]]
Reranker = Callable[..., list[RetrievalCandidate]]


async def hybrid_search(
    query_text: str,
    *,
    session: Any,
    opensearch_client: Any,
    embedding_model: Any = None,
    reranker_model: Any = None,
    filters: RetrievalFilters | None = None,
    top_k: int | None = None,
    rerank_top_k: int | None = None,
    dense_searcher: DenseSearcher = search_dense_chunks,
    keyword_searcher: KeywordSearcher = search_keyword_chunks,
    reranker: Reranker = rerank_results,
) -> HybridSearchResult:
    """Run query embedding, dense/BM25 retrieval, RRF, reranking, and formatting."""
    settings = get_settings()
    retrieval_top_k = top_k or settings.retrieval_top_k
    final_top_k = rerank_top_k or settings.rerank_top_k
    dense_error = None
    keyword_error = None

    try:
        query_embedding = embed_query(query_text, model=embedding_model, model_name=settings.embedding_model)
        dense_candidates = await dense_searcher(
            session,
            query_embedding,
            filters=filters,
            top_k=retrieval_top_k,
            embedding_dim=settings.embedding_dim,
        )
    except Exception as exc:
        dense_candidates = []
        dense_error = str(exc)

    try:
        keyword_candidates = keyword_searcher(
            opensearch_client,
            query_text,
            filters=filters,
            top_k=retrieval_top_k,
            index_name=settings.opensearch_index,
        )
    except Exception as exc:
        keyword_candidates = []
        keyword_error = str(exc)

    if not dense_candidates and not keyword_candidates:
        raise RetrievalError("Both dense and keyword retrieval failed or returned no candidates")

    fused = reciprocal_rank_fusion(
        dense_candidates,
        keyword_candidates,
        top_k=retrieval_top_k,
    )
    reranker_error = None
    try:
        reranked = reranker(
            query_text,
            fused,
            model=reranker_model,
            top_k=final_top_k,
        )
    except Exception as exc:
        reranker_error = str(exc)
        reranked = _fallback_reranked(fused, top_k=final_top_k)

    return HybridSearchResult(
        query_text=query_text,
        candidates=reranked,
        search_results=candidates_to_search_results(reranked),
        evidence_cards=candidates_to_evidence_cards(reranked),
        dense_error=dense_error,
        keyword_error=keyword_error,
        reranker_error=reranker_error,
    )


def _fallback_reranked(candidates: list[RetrievalCandidate], *, top_k: int) -> list[RetrievalCandidate]:
    fallback = [
        candidate.with_updates(
            rerank_score=candidate.rrf_score if candidate.rrf_score is not None else candidate.score,
            reranker_failed=True,
        )
        for candidate in candidates[:top_k]
    ]
    return [candidate.with_updates(rank=rank) for rank, candidate in enumerate(fallback, start=1)]