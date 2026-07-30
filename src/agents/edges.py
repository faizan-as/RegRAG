"""Conditional routing helpers for the Phase 4 LangGraph workflow."""

from __future__ import annotations

from src.agents.guardrails import can_retry
from src.agents.state import AgentState


def route_after_confidence(state: AgentState) -> str:
    """Route low-confidence or refused states to response, otherwise generation."""
    if state.get("refused") or not state.get("confidence_sufficient", False):
        return "respond"
    return "generate_answer"


def route_after_citation_binding(state: AgentState) -> str:
    """Route citation binding success, retry, or refusal."""
    binding = state.get("citation_binding")
    if binding and binding.success:
        return "faithfulness_guard"
    if can_retry(state.get("retry_count", 0), state.get("max_retries", 0)):
        return "generate_answer"
    return "respond"


def route_after_faithfulness(state: AgentState) -> str:
    """Route faithfulness success, retry, or terminal refusal."""
    if state.get("faithfulness_passed", False):
        return "respond"
    if can_retry(state.get("retry_count", 0), state.get("max_retries", 0)):
        return "generate_answer"
    return "respond"