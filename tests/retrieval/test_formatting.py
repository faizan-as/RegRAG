"""Tests for retrieval output formatting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.api.schemas.search import RetrievalSource
from src.retrieval.formatting import (
    EvidenceFormattingError,
    candidate_to_evidence_card,
    candidates_to_search_results,
    confidence_from_rerank_score,
)
from tests.retrieval.utils import candidate


def test_candidate_to_evidence_card_builds_required_payload() -> None:
    item = candidate("a", RetrievalSource.RERANKED, score=0.2, rrf_score=0.2, rerank_score=1.0)
    retrieved_at = datetime(2026, 7, 22, tzinfo=UTC)

    card = candidate_to_evidence_card(item, citation_id="[1]", retrieved_at=retrieved_at)

    assert card.citation_id == "[1]"
    assert card.document_id == "example-guidance"
    assert card.title == "Example Guidance"
    assert card.page_number == 3
    assert card.retrieval_score == 0.2
    assert card.rerank_score == 1.0
    assert card.confidence == pytest.approx(confidence_from_rerank_score(1.0))
    assert card.retrieved_at == retrieved_at


def test_candidate_to_evidence_card_fails_closed_on_missing_rerank_score() -> None:
    item = candidate("a", RetrievalSource.FUSED, score=0.2, rrf_score=0.2, rerank_score=None)

    with pytest.raises(EvidenceFormattingError, match="rerank_score"):
        candidate_to_evidence_card(item, citation_id="[1]")


def test_candidate_to_evidence_card_uses_zero_confidence_when_reranker_failed() -> None:
    item = candidate(
        "a",
        RetrievalSource.FUSED,
        score=0.2,
        rrf_score=0.2,
        rerank_score=0.2,
        reranker_failed=True,
    )

    card = candidate_to_evidence_card(item, citation_id="[1]")

    assert card.confidence == 0.0


def test_candidates_to_search_results_preserves_scores() -> None:
    item = candidate("a", RetrievalSource.RERANKED, score=1.0, dense_score=0.8, keyword_score=7.0, rrf_score=0.2, rerank_score=1.0)

    result = candidates_to_search_results([item])[0]

    assert result.chunk.chunk_id == "a"
    assert result.source == RetrievalSource.RERANKED
    assert result.dense_score == 0.8
    assert result.keyword_score == 7.0
    assert result.rrf_score == 0.2
    assert result.rerank_score == 1.0