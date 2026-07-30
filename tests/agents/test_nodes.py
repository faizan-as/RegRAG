"""Tests for Phase 4 workflow nodes."""

from __future__ import annotations

from apps.api.settings import Settings
from src.agents.guardrails import FaithfulnessResult
from src.agents.nodes import AgentNodeDependencies, AgentWorkflowNodes
from src.agents.state import initial_agent_state
from tests.agents.utils import FakeLLM, fake_retrieval


class PassingValidator:
    async def validate(self, *, answer_text, evidence_cards):
        del answer_text, evidence_cards
        return FaithfulnessResult(passed=True, score=1.0)


async def test_nodes_success_path_produces_answer() -> None:
    llm = FakeLLM([
        '{"rewritten_query":"rewritten","intent":"question","entities":{"center":["CDER"]}}',
        "FDA guidance supports this point [1].",
    ])
    nodes = AgentWorkflowNodes(
        AgentNodeDependencies(
            llm_client=llm,
            retrieval=fake_retrieval,
            faithfulness_validator=PassingValidator(),
            settings=Settings(CONFIDENCE_THRESHOLD=0.1),
        )
    )
    state = initial_agent_state("query", filters={"center": "CDER", "unknown": "ignored"})
    for node in [
        nodes.query_understand,
        nodes.retrieval_router,
        nodes.hybrid_retrieve,
        nodes.merge_rerank,
        nodes.confidence_check,
        nodes.generate_answer,
        nodes.citation_bind,
        nodes.faithfulness_guard,
        nodes.respond,
    ]:
        state.update(await node(state))

    assert state["answer"].refused is False
    assert state["answer"].evidence[0].citation_id == "[1]"
    assert state["ignored_filter_keys"] == ["unknown"]


async def test_confidence_node_refuses_without_evidence() -> None:
    nodes = AgentWorkflowNodes(
        AgentNodeDependencies(llm_client=FakeLLM([]), retrieval=fake_retrieval, settings=Settings())
    )
    state = initial_agent_state("query")
    state.update(await nodes.confidence_check(state))

    assert state["refused"] is True
    assert state["refusal"].reason == "no_evidence"