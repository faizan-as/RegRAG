"""Tests for citation-first prompt templates."""

from __future__ import annotations

from apps.api.schemas.search import RetrievalSource
from src.llm.prompts import build_grounded_answer_prompt, format_evidence_context
from src.retrieval.formatting import candidates_to_evidence_cards
from tests.retrieval.utils import candidate


def test_evidence_context_preserves_citation_metadata() -> None:
    cards = candidates_to_evidence_cards([candidate("one", RetrievalSource.RERANKED, rerank_score=1.0)])

    context = format_evidence_context(cards)

    assert "[1] Example Guidance" in context
    assert "retrieval=" in context
    assert "Passage:" in context


def test_grounded_prompt_contains_citation_and_boundary_instructions() -> None:
    cards = candidates_to_evidence_cards([candidate("one", RetrievalSource.RERANKED, rerank_score=1.0)])

    prompt = build_grounded_answer_prompt("question", cards)

    assert "Do not renumber citations" in prompt
    assert "Do not make final legal" in prompt
    assert "[1]" in prompt