"""Tests for conditional workflow routing."""

from __future__ import annotations

from src.agents.edges import (
    route_after_citation_binding,
    route_after_confidence,
    route_after_faithfulness,
)
from src.agents.state import CitationBindingResult


def test_confidence_routes() -> None:
    assert route_after_confidence({"confidence_sufficient": True}) == "generate_answer"
    assert route_after_confidence({"confidence_sufficient": False}) == "respond"


def test_citation_routes_retry_success_and_exhausted() -> None:
    assert route_after_citation_binding(
        {"citation_binding": CitationBindingResult(success=True), "retry_count": 0, "max_retries": 1}
    ) == "faithfulness_guard"
    assert route_after_citation_binding(
        {"citation_binding": CitationBindingResult(success=False), "retry_count": 0, "max_retries": 1}
    ) == "generate_answer"
    assert route_after_citation_binding(
        {"citation_binding": CitationBindingResult(success=False), "retry_count": 1, "max_retries": 1}
    ) == "respond"


def test_faithfulness_routes() -> None:
    assert route_after_faithfulness({"faithfulness_passed": True}) == "respond"
    assert route_after_faithfulness(
        {"faithfulness_passed": False, "retry_count": 0, "max_retries": 1}
    ) == "generate_answer"
    assert route_after_faithfulness(
        {"faithfulness_passed": False, "retry_count": 1, "max_retries": 1}
    ) == "respond"