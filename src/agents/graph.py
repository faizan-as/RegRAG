"""LangGraph assembly for the Phase 4 citation-first workflow."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from apps.api.settings import get_settings
from src.agents.edges import (
    route_after_citation_binding,
    route_after_confidence,
    route_after_faithfulness,
)
from src.agents.nodes import AgentNodeDependencies, AgentWorkflowNodes
from src.agents.state import AgentState, initial_agent_state
from src.llm.router import LLMClient, build_llm_client


def build_agent_graph(dependencies: AgentNodeDependencies | None = None) -> Any:
    """Build and compile the MVP LangGraph workflow."""
    if dependencies is None:
        dependencies = AgentNodeDependencies(llm_client=build_llm_client())
    nodes = AgentWorkflowNodes(dependencies)
    graph = StateGraph(AgentState)
    graph.add_node("query_understand", nodes.query_understand)
    graph.add_node("retrieval_router", nodes.retrieval_router)
    graph.add_node("hybrid_retrieve", nodes.hybrid_retrieve)
    graph.add_node("merge_rerank", nodes.merge_rerank)
    graph.add_node("confidence_check", nodes.confidence_check)
    graph.add_node("generate_answer", nodes.generate_answer)
    graph.add_node("citation_bind", nodes.citation_bind)
    graph.add_node("faithfulness_guard", nodes.faithfulness_guard)
    graph.add_node("respond", nodes.respond)

    graph.set_entry_point("query_understand")
    graph.add_edge("query_understand", "retrieval_router")
    graph.add_edge("retrieval_router", "hybrid_retrieve")
    graph.add_edge("hybrid_retrieve", "merge_rerank")
    graph.add_edge("merge_rerank", "confidence_check")
    graph.add_conditional_edges(
        "confidence_check",
        route_after_confidence,
        {"generate_answer": "generate_answer", "respond": "respond"},
    )
    graph.add_conditional_edges(
        "generate_answer",
        lambda state: "respond" if state.get("refused") else "citation_bind",
        {"citation_bind": "citation_bind", "respond": "respond"},
    )
    graph.add_conditional_edges(
        "citation_bind",
        route_after_citation_binding,
        {
            "generate_answer": "generate_answer",
            "faithfulness_guard": "faithfulness_guard",
            "respond": "respond",
        },
    )
    graph.add_conditional_edges(
        "faithfulness_guard",
        route_after_faithfulness,
        {"generate_answer": "generate_answer", "respond": "respond"},
    )
    graph.add_edge("respond", END)
    return graph.compile()


async def run_agent(
    query: str,
    *,
    session_id: str | None = None,
    filters: dict[str, str] | None = None,
    llm_client: LLMClient | None = None,
    dependencies: AgentNodeDependencies | None = None,
) -> AgentState:
    """Run the compiled agent graph and return final state."""
    settings = get_settings()
    if dependencies is None:
        dependencies = AgentNodeDependencies(llm_client=llm_client or build_llm_client(), settings=settings)
    graph = build_agent_graph(dependencies)
    state = initial_agent_state(
        query,
        session_id=session_id,
        filters=filters,
        max_retries=settings.max_faithfulness_retries,
    )
    return await graph.ainvoke(state)