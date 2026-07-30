"""Plain async workflow nodes for the Phase 4 citation-first agent."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from apps.api.schemas.answer import Answer
from apps.api.settings import Settings, get_settings
from src.agents.citation import bind_citations
from src.agents.guardrails import (
    FaithfulnessValidator,
    PermissiveFaithfulnessValidator,
    aggregate_confidence,
    confidence_is_sufficient,
    contains_compliance_determination,
    refusal,
)
from src.agents.state import AgentState, ExecutionTraceEntry, QueryUnderstanding, append_trace
from src.common.logging import get_logger
from src.llm.prompts import (
    GROUNDED_ANSWER_PROMPT_VERSION,
    build_grounded_answer_prompt,
    build_query_understand_prompt,
)
from src.llm.router import LLMClient
from src.retrieval.client import hybrid_search
from src.retrieval.filters import RetrievalFilters
from src.retrieval.models import HybridSearchResult

logger = get_logger(__name__)
RetrievalCallable = Callable[..., Awaitable[HybridSearchResult]]


class AgentNodeDependencies:
    """Injectable dependencies used by workflow nodes."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        retrieval: RetrievalCallable = hybrid_search,
        session_factory: Callable[[], Any] | None = None,
        opensearch_client_factory: Callable[[], Any] | None = None,
        embedding_model: Any = None,
        reranker_model: Any = None,
        faithfulness_validator: FaithfulnessValidator | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.retrieval = retrieval
        self.session_factory = session_factory or (lambda: None)
        self.opensearch_client_factory = opensearch_client_factory or (lambda: None)
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.faithfulness_validator = faithfulness_validator or PermissiveFaithfulnessValidator()
        self.settings = settings or get_settings()


class AgentWorkflowNodes:
    """Collection of independently testable async node functions."""

    def __init__(self, dependencies: AgentNodeDependencies) -> None:
        self.dependencies = dependencies

    async def query_understand(self, state: AgentState) -> AgentState:
        """Rewrite, classify, and extract FDA entities from the user query."""
        started_at = datetime.now(UTC)
        status = "success"
        diagnostics: dict[str, Any] = {}
        try:
            prompt = build_query_understand_prompt(state["query"])
            raw = await self.dependencies.llm_client.generate(prompt, temperature=0.0, max_tokens=500)
            understanding = _parse_understanding(raw, fallback_query=state["query"])
        except Exception as exc:
            logger.warning("query_understand_failed", error=str(exc))
            understanding = QueryUnderstanding(rewritten_query=state["query"])
            status = "failed"
            diagnostics = {"fallback": "original_query"}
        trace = ExecutionTraceEntry(
            node="query_understand",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status=status,
            provider=self.dependencies.llm_client.provider_name,
            diagnostics=diagnostics,
        )
        return AgentState(
            understanding=understanding,
            rewritten_query=understanding.rewritten_query,
            intent=understanding.intent,
            entities=understanding.entities,
            execution_trace=append_trace(state, trace),
        )

    async def retrieval_router(self, state: AgentState) -> AgentState:
        """Normalize request filters and select the MVP retrieval route."""
        started_at = datetime.now(UTC)
        filters, ignored = _normalize_filters(state.get("raw_filters", {}))
        has_filters = bool(filters.model_dump(exclude_none=True, exclude_defaults=True))
        route = "metadata_constrained" if has_filters else "hybrid"
        trace = ExecutionTraceEntry(
            node="retrieval_router",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            diagnostics={"ignored_filter_keys": ignored, "route": route},
        )
        return AgentState(
            filters=filters,
            ignored_filter_keys=ignored,
            retrieval_route=route,
            execution_trace=append_trace(state, trace),
        )

    async def hybrid_retrieve(self, state: AgentState) -> AgentState:
        """Run Phase 3 hybrid retrieval with injected dependencies."""
        started_at = datetime.now(UTC)
        try:
            result = await self.dependencies.retrieval(
                state.get("rewritten_query") or state["query"],
                session=self.dependencies.session_factory(),
                opensearch_client=self.dependencies.opensearch_client_factory(),
                embedding_model=self.dependencies.embedding_model,
                reranker_model=self.dependencies.reranker_model,
                filters=state.get("filters"),
            )
            diagnostics = {
                "dense_error": result.dense_error,
                "keyword_error": result.keyword_error,
                "reranker_error": result.reranker_error,
            }
            trace = ExecutionTraceEntry(
                node="hybrid_retrieve",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                evidence_count=len(result.evidence_cards),
                diagnostics=diagnostics,
            )
            return AgentState(
                hybrid_result=result,
                candidates=result.candidates,
                search_results=result.search_results,
                evidence_cards=result.evidence_cards,
                retrieval_diagnostics=diagnostics,
                execution_trace=append_trace(state, trace),
            )
        except Exception as exc:
            trace = ExecutionTraceEntry(
                node="hybrid_retrieve",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                status="failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return AgentState(
                refused=True,
                refusal=refusal("retrieval_failure"),
                retrieval_errors=[*state.get("retrieval_errors", []), str(exc)],
                execution_trace=append_trace(state, trace),
            )

    async def merge_rerank(self, state: AgentState) -> AgentState:
        """Record Phase 3 reranked retrieval output without duplicating retrieval logic."""
        started_at = datetime.now(UTC)
        evidence = state.get("evidence_cards", [])
        trace = ExecutionTraceEntry(
            node="merge_rerank",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            evidence_count=len(evidence),
            diagnostics=state.get("retrieval_diagnostics", {}),
        )
        return AgentState(execution_trace=append_trace(state, trace))

    async def confidence_check(self, state: AgentState) -> AgentState:
        """Compute answer-level confidence and refuse weak evidence."""
        started_at = datetime.now(UTC)
        evidence = state.get("evidence_cards", [])
        confidence = aggregate_confidence(evidence)
        sufficient = confidence_is_sufficient(
            confidence,
            threshold=self.dependencies.settings.confidence_threshold,
        )
        update: AgentState = AgentState(confidence=confidence, confidence_sufficient=sufficient)
        if state.get("refused"):
            pass
        elif not evidence:
            update.update(refused=True, refusal=refusal("no_evidence"))
        elif not sufficient:
            update.update(refused=True, refusal=refusal("low_confidence"))
        trace = ExecutionTraceEntry(
            node="confidence_check",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            evidence_count=len(evidence),
            confidence=confidence,
        )
        update["execution_trace"] = append_trace(state, trace)
        return update

    async def generate_answer(self, state: AgentState) -> AgentState:
        """Generate a grounded answer that must cite Evidence Card ids."""
        started_at = datetime.now(UTC)
        retry_count = state.get("retry_count", 0)
        prompt = build_grounded_answer_prompt(
            state.get("rewritten_query") or state["query"],
            state.get("evidence_cards", []),
        )
        try:
            answer = await self.dependencies.llm_client.generate(prompt, temperature=0.0)
            update: AgentState = AgentState(
                generated_answer=answer,
                prompt_version=GROUNDED_ANSWER_PROMPT_VERSION,
                llm_provider=self.dependencies.llm_client.provider_name,
                retry_count=retry_count,
                refused=False,
            )
            if contains_compliance_determination(answer):
                update.update(
                    refused=True,
                    refusal=refusal("compliance_determination_risk"),
                    guardrail_errors=[
                        *state.get("guardrail_errors", []),
                        "Generated answer contained prohibited compliance determination.",
                    ],
                )
            status = "success"
            error_message = None
            error_type = None
        except Exception as exc:
            update = AgentState(refused=True, refusal=refusal("unsupported_query"))
            status = "failed"
            error_type = type(exc).__name__
            error_message = str(exc)
        trace = ExecutionTraceEntry(
            node="generate_answer",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status=status,
            error_type=error_type,
            error_message=error_message,
            provider=self.dependencies.llm_client.provider_name,
            evidence_count=len(state.get("evidence_cards", [])),
            retry_count=retry_count,
        )
        update["execution_trace"] = append_trace(state, trace)
        return update

    async def citation_bind(self, state: AgentState) -> AgentState:
        """Bind model-emitted citations to available Evidence Cards."""
        started_at = datetime.now(UTC)
        binding = bind_citations(state.get("generated_answer", ""), state.get("evidence_cards", []))
        retry_count = state.get("retry_count", 0)
        update = AgentState(citation_binding=binding, bound_evidence=binding.bound_cards)
        if not binding.success:
            next_retry_count = retry_count + 1
            update["retry_count"] = next_retry_count
            update["guardrail_errors"] = [
                *state.get("guardrail_errors", []),
                binding.error or "Citation binding failed.",
            ]
            if next_retry_count >= state.get("max_retries", 0):
                update.update(refused=True, refusal=refusal("citation_binding_failure"))
        trace = ExecutionTraceEntry(
            node="citation_bind",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status="success" if binding.success else "failed",
            evidence_count=len(binding.bound_cards),
            retry_count=update.get("retry_count", retry_count),
            diagnostics={"cited_ids": binding.cited_ids, "missing_ids": binding.missing_ids},
        )
        update["execution_trace"] = append_trace(state, trace)
        return update

    async def faithfulness_guard(self, state: AgentState) -> AgentState:
        """Validate the generated answer against bound evidence."""
        started_at = datetime.now(UTC)
        result = await self.dependencies.faithfulness_validator.validate(
            answer_text=state.get("generated_answer", ""),
            evidence_cards=state.get("bound_evidence", []),
        )
        update = AgentState(faithfulness_passed=result.passed, faithfulness_reason=result.reason)
        retry_count = state.get("retry_count", 0)
        if not result.passed:
            retry_count += 1
            update["retry_count"] = retry_count
            update["guardrail_errors"] = [
                *state.get("guardrail_errors", []),
                result.reason or "Faithfulness failed.",
            ]
            if retry_count >= state.get("max_retries", 0):
                update.update(refused=True, refusal=refusal("faithfulness_failure"))
        trace = ExecutionTraceEntry(
            node="faithfulness_guard",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            status="success" if result.passed else "failed",
            confidence=result.score,
            retry_count=update.get("retry_count", retry_count),
            diagnostics={"reason": result.reason},
        )
        update["execution_trace"] = append_trace(state, trace)
        return update

    async def respond(self, state: AgentState) -> AgentState:
        """Create the authoritative final Answer payload."""
        started_at = datetime.now(UTC)
        refused = state.get("refused", False)
        refusal_meta = state.get("refusal")
        evidence = [] if refused else state.get("bound_evidence", [])
        if not refused and not evidence:
            refused = True
            refusal_meta = refusal("citation_binding_failure")
            evidence = []
        text = refusal_meta.message if refused and refusal_meta else state.get("generated_answer", "")
        answer = Answer(
            text=text,
            evidence=evidence,
            confidence=state.get("confidence", 0.0),
            refused=refused,
            refusal_reason=refusal_meta.reason if refused and refusal_meta else None,
            session_id=state.get("session_id"),
        )
        trace = ExecutionTraceEntry(
            node="respond",
            started_at=started_at,
            completed_at=datetime.now(UTC),
            evidence_count=len(evidence),
            confidence=answer.confidence,
        )
        return AgentState(answer=answer, execution_trace=append_trace(state, trace))


def _parse_understanding(raw: str, *, fallback_query: str) -> QueryUnderstanding:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return QueryUnderstanding(rewritten_query=fallback_query)
    return QueryUnderstanding(
        rewritten_query=str(data.get("rewritten_query") or fallback_query),
        intent=data.get("intent") or "question",
        entities=data.get("entities") or {},
    )


def _normalize_filters(raw_filters: dict[str, str]) -> tuple[RetrievalFilters, list[str]]:
    allowed = set(RetrievalFilters.model_fields)
    data: dict[str, Any] = {key: value for key, value in raw_filters.items() if key in allowed}
    ignored = sorted(key for key in raw_filters if key not in allowed)
    list_fields = {"topics", "cfr_references", "product_codes"}
    for field in list_fields:
        if field in data and isinstance(data[field], str):
            data[field] = [item.strip() for item in data[field].split(",") if item.strip()]
    return RetrievalFilters.model_validate(data), ignored