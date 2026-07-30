"""Shared fixtures for agent workflow tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

from apps.api.schemas.search import RetrievalSource
from src.retrieval.formatting import candidates_to_evidence_cards, candidates_to_search_results
from src.retrieval.models import HybridSearchResult
from tests.retrieval.utils import candidate


class FakeLLM:
    """Simple fake LLM returning queued responses."""

    provider_name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs) -> str:
        del kwargs
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else "Supported answer [1]."

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        del kwargs
        self.prompts.append(prompt)
        for token in ["Supported", " answer", " [1]."]:
            yield token


async def fake_retrieval(query_text: str, **kwargs) -> HybridSearchResult:
    """Return one high-confidence retrieval result."""
    del kwargs
    items = [
        candidate(
            "one",
            RetrievalSource.RERANKED,
            score=1.0,
            rrf_score=0.9,
            rerank_score=2.0,
            rank=1,
        )
    ]
    return HybridSearchResult(
        query_text=query_text,
        candidates=items,
        search_results=candidates_to_search_results(items),
        evidence_cards=candidates_to_evidence_cards(items),
    )