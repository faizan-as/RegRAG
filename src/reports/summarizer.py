"""Grounded, citation-first guidance summarization (summaries, requirements, changes)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.summaries import SummaryRequest, SummaryResult, SummaryType
from apps.api.settings import Settings, get_settings
from src.agents.citation import bind_citations
from src.agents.guardrails import (
    FaithfulnessValidator,
    PermissiveFaithfulnessValidator,
    aggregate_confidence,
    confidence_is_sufficient,
)
from src.db.models import GuidanceChunk, GuidanceRegistry
from src.llm.prompts import build_summary_prompt
from src.llm.router import LLMClient
from src.retrieval.client import RetrievalError, hybrid_search
from src.retrieval.filters import RetrievalFilters


@dataclass
class SummaryDependencies:
    """Injectable dependencies for grounded document summarization."""

    llm_client: LLMClient
    session_factory: Callable[[], AsyncSession]
    opensearch_client: Any
    embedding_model: Any = None
    reranker_model: Any = None
    faithfulness_validator: FaithfulnessValidator | None = None
    settings: Settings | None = None


async def _document_versions(
    session: AsyncSession, document_slug: str
) -> tuple[GuidanceRegistry | None, list[str]]:
    registry = await session.get(GuidanceRegistry, document_slug)
    if registry is None:
        return None, []
    rows = await session.execute(
        select(GuidanceChunk.version_hash, GuidanceChunk.created_at)
        .where(GuidanceChunk.document_slug == document_slug)
        .order_by(GuidanceChunk.created_at.desc())
    )
    versions = list(dict.fromkeys(version_hash for version_hash, _ in rows))
    return registry, versions


async def _retrieve_version_evidence(
    query: str,
    version_hash: str,
    request: SummaryRequest,
    dependencies: SummaryDependencies,
) -> list[EvidenceCard]:
    session = dependencies.session_factory()
    try:
        result = await hybrid_search(
            query,
            session=session,
            opensearch_client=dependencies.opensearch_client,
            embedding_model=dependencies.embedding_model,
            reranker_model=dependencies.reranker_model,
            filters=RetrievalFilters(
                document_slug=request.document_id,
                version_hash=version_hash,
            ),
            top_k=20,
            rerank_top_k=10,
        )
        return result.evidence_cards
    except RetrievalError:
        return []
    finally:
        await session.close()


def _refuse(request: SummaryRequest, reason: str, message: str) -> SummaryResult:
    return SummaryResult(
        document_id=request.document_id,
        summary_type=request.summary_type,
        text=message,
        evidence=[],
        refused=True,
        refusal_reason=reason,
    )


async def generate_summary(
    request: SummaryRequest, *, dependencies: SummaryDependencies
) -> SummaryResult:
    """Generate a version-scoped, citation-bound, faithfulness-checked summary."""
    settings = dependencies.settings or get_settings()
    session = dependencies.session_factory()
    try:
        registry, versions = await _document_versions(session, request.document_id)
    finally:
        await session.close()

    if registry is None:
        return _refuse(request, "not_found", "The requested FDA guidance document was not found.")

    if not versions:
        return _refuse(
            request,
            "no_evidence",
            "No indexed FDA guidance evidence is available for this document.",
        )

    current_version = versions[0]
    if request.summary_type == SummaryType.KEY_CHANGES and not request.compare_version_hash:
        return _refuse(
            request, "comparison_required", "A prior version hash is required for key changes."
        )
    if request.compare_version_hash and request.compare_version_hash not in versions:
        return _refuse(
            request, "version_not_found", "The requested comparison version was not found."
        )

    query = {
        SummaryType.SUMMARY: f"Summarize the FDA guidance {registry.title}",
        SummaryType.KEY_REQUIREMENTS: f"Key regulatory requirements in {registry.title}",
        SummaryType.KEY_CHANGES: f"Material changes in {registry.title}",
    }[request.summary_type]
    evidence_cards = await _retrieve_version_evidence(query, current_version, request, dependencies)
    if request.summary_type == SummaryType.KEY_CHANGES and request.compare_version_hash:
        previous_cards = await _retrieve_version_evidence(
            query, request.compare_version_hash, request, dependencies
        )
        combined = [*previous_cards, *evidence_cards]
        evidence_cards = [
            card.model_copy(update={"citation_id": f"[{index}]"})
            for index, card in enumerate(combined, start=1)
        ]

    if not evidence_cards:
        return _refuse(
            request,
            "no_evidence",
            "No ranked FDA guidance evidence is available for this document.",
        )

    confidence = aggregate_confidence(evidence_cards)
    if not confidence_is_sufficient(confidence, threshold=settings.confidence_threshold):
        return _refuse(
            request, "low_confidence", "Available evidence is too weak to summarize this document."
        )

    prompt = build_summary_prompt(registry.title, request.summary_type.value, evidence_cards)
    generated_text = await dependencies.llm_client.generate(prompt, temperature=0.0, max_tokens=800)

    binding = bind_citations(generated_text, evidence_cards)
    if not binding.success:
        return _refuse(
            request,
            "citation_binding_failure",
            "The generated summary could not be bound to cited evidence.",
        )

    validator = dependencies.faithfulness_validator or PermissiveFaithfulnessValidator()
    faithfulness = await validator.validate(
        answer_text=generated_text, evidence_cards=binding.bound_cards
    )
    if not faithfulness.passed:
        return _refuse(
            request,
            "faithfulness_failure",
            "The generated summary could not be validated against the cited evidence.",
        )

    return SummaryResult(
        document_id=request.document_id,
        summary_type=request.summary_type,
        text=generated_text,
        evidence=binding.bound_cards or [],
        current_version_hash=current_version,
        previous_version_hash=request.compare_version_hash,
        faithfulness_passed=True,
    )
