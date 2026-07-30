"""Tests for fail-closed citation binding."""

from __future__ import annotations

from apps.api.schemas.search import RetrievalSource
from src.agents.citation import bind_citations
from src.retrieval.formatting import candidates_to_evidence_cards
from tests.retrieval.utils import candidate


def _cards():
    return candidates_to_evidence_cards(
        [
            candidate("one", RetrievalSource.RERANKED, rerank_score=1.0, rank=1),
            candidate("two", RetrievalSource.RERANKED, rerank_score=0.5, rank=2),
        ]
    )


def test_bind_valid_repeated_and_out_of_order_markers() -> None:
    result = bind_citations("Second point [2]. First point [1]. Again [2].", _cards())

    assert result.success is True
    assert result.cited_ids == ["[2]", "[1]"]
    assert [card.citation_id for card in result.bound_cards] == ["[2]", "[1]"]


def test_bind_fails_without_citations() -> None:
    result = bind_citations("No marker here.", _cards())

    assert result.success is False
    assert result.error == "Generated answer contains no citations."


def test_bind_fails_for_unknown_citation() -> None:
    result = bind_citations("Unknown [3].", _cards())

    assert result.success is False
    assert result.missing_ids == ["[3]"]