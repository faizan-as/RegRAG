"""Tests for confidence, refusal, and retry guardrails."""

from __future__ import annotations

from apps.api.schemas.search import RetrievalSource
from src.agents.guardrails import (
    aggregate_confidence,
    can_retry,
    confidence_is_sufficient,
    contains_compliance_determination,
    refusal,
)
from src.retrieval.formatting import candidates_to_evidence_cards
from tests.retrieval.utils import candidate


def test_aggregate_confidence_uses_max_card_confidence() -> None:
    cards = candidates_to_evidence_cards(
        [
            candidate("one", RetrievalSource.RERANKED, rerank_score=-1.0),
            candidate("two", RetrievalSource.RERANKED, rerank_score=2.0),
        ]
    )

    assert aggregate_confidence(cards) == max(card.confidence for card in cards)


def test_confidence_threshold_and_retry_helpers() -> None:
    assert confidence_is_sufficient(0.7, threshold=0.5) is True
    assert confidence_is_sufficient(0.2, threshold=0.5) is False
    assert can_retry(0, 1) is True
    assert can_retry(1, 1) is False


def test_compliance_determination_detection() -> None:
    assert contains_compliance_determination("FDA will approve this submission.") is True
    assert contains_compliance_determination("FDA guidance describes submission content.") is False


def test_refusal_builder() -> None:
    metadata = refusal("low_confidence")

    assert metadata.reason == "low_confidence"
    assert "too weak" in metadata.message