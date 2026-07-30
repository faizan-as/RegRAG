"""Tests for LangGraph assembly and bounded workflow paths."""

from __future__ import annotations

from apps.api.settings import Settings
from src.agents.graph import build_agent_graph
from src.agents.guardrails import FaithfulnessResult
from src.agents.nodes import AgentNodeDependencies
from src.agents.state import initial_agent_state
from tests.agents.utils import FakeLLM, fake_retrieval


class PassingValidator:
    async def validate(self, *, answer_text, evidence_cards):
        del answer_text, evidence_cards
        return FaithfulnessResult(passed=True, score=1.0)


async def test_graph_success_path_reaches_respond() -> None:
    graph = build_agent_graph(
        AgentNodeDependencies(
            llm_client=FakeLLM([
                '{"rewritten_query":"query","intent":"question","entities":{}}',
                "Answer [1].",
            ]),
            retrieval=fake_retrieval,
            faithfulness_validator=PassingValidator(),
            settings=Settings(CONFIDENCE_THRESHOLD=0.1, MAX_FAITHFULNESS_RETRIES=1),
        )
    )
    result = await graph.ainvoke(initial_agent_state("query", max_retries=1))

    assert result["answer"].refused is False
    assert result["execution_trace"][-1].node == "respond"


async def test_graph_refusal_path_reaches_respond() -> None:
    async def empty_retrieval(query_text: str, **kwargs):
        del query_text, kwargs
        from src.retrieval.models import HybridSearchResult

        return HybridSearchResult(query_text="query", candidates=[], search_results=[], evidence_cards=[])

    graph = build_agent_graph(
        AgentNodeDependencies(
            llm_client=FakeLLM(['{"rewritten_query":"query","intent":"question","entities":{}}']),
            retrieval=empty_retrieval,
            settings=Settings(CONFIDENCE_THRESHOLD=0.5, MAX_FAITHFULNESS_RETRIES=1),
        )
    )
    result = await graph.ainvoke(initial_agent_state("query", max_retries=1))

    assert result["answer"].refused is True
    assert result["answer"].refusal_reason == "no_evidence"