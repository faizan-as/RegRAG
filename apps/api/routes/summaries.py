"""Grounded summary and version-comparison routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.audit import add_audit_event
from apps.api.deps import get_db_session, get_resources
from apps.api.errors import NotFoundAPIError, RetrievalUnavailableError
from apps.api.ratelimit import enforce_summary_rate_limit
from apps.api.resources import AppResources
from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.summaries import SummaryRequest, SummaryResult
from apps.api.security import AuthenticatedUser, require_roles
from src.common.clients import get_postgres_sessionmaker
from src.db.models import GroundedSummaryRecord
from src.reports.summarizer import SummaryDependencies, generate_summary

router = APIRouter(prefix="/api/summaries", tags=["summaries"])


def _summary_result(record: GroundedSummaryRecord) -> SummaryResult:
    return SummaryResult(
        summary_id=str(record.id),
        document_id=record.document_slug or "",
        summary_type=record.summary_type,
        text=record.text,
        evidence=[EvidenceCard.model_validate(card) for card in record.evidence],
        refused=record.refused,
        refusal_reason=record.refusal_reason,
        current_version_hash=record.current_version_hash,
        previous_version_hash=record.previous_version_hash,
        faithfulness_passed=record.guardrail_metadata.get("faithfulness_passed"),
        generated_at=record.created_at,
    )


@router.post("", response_model=SummaryResult, dependencies=[Depends(enforce_summary_rate_limit)])
async def create_summary(
    payload: SummaryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    resources: AppResources = Depends(get_resources),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> SummaryResult:
    """Generate and persist a citation-bound grounded summary or refusal."""
    if resources.llm_client is None:
        raise RetrievalUnavailableError("Summary generation is currently unavailable.")
    sessionmaker = get_postgres_sessionmaker()
    result = await generate_summary(
        payload,
        dependencies=SummaryDependencies(
            llm_client=resources.llm_client,
            session_factory=lambda: sessionmaker(),
            opensearch_client=resources.opensearch_client,
            embedding_model=resources.embedding_model,
            reranker_model=resources.reranker_model,
            settings=resources.settings,
        ),
    )
    record = GroundedSummaryRecord(
        owner_user_id=user.user_id,
        document_slug=payload.document_id,
        summary_type=payload.summary_type.value,
        current_version_hash=result.current_version_hash,
        previous_version_hash=result.previous_version_hash,
        text=result.text,
        evidence=[card.model_dump(mode="json") for card in result.evidence],
        refused=result.refused,
        refusal_reason=result.refusal_reason,
        guardrail_metadata={"faithfulness_passed": result.faithfulness_passed},
        comparison_metadata={
            "current_version_hash": result.current_version_hash,
            "previous_version_hash": result.previous_version_hash,
        },
    )
    db.add(record)
    await db.flush()
    add_audit_event(
        db,
        event_type="summary_refused" if result.refused else "summary_completed",
        user_id=user.user_id,
        session_id=None,
        route="/api/summaries",
        request_id=request.state.request_id,
        payload={"summary_id": str(record.id), "document_id": payload.document_id},
    )
    await db.commit()
    return result.model_copy(update={"summary_id": str(record.id)})


@router.get("/{summary_id}", response_model=SummaryResult)
async def get_summary(
    summary_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> SummaryResult:
    """Return a durable grounded summary owned by the caller."""
    record = await db.get(GroundedSummaryRecord, summary_id)
    if record is None or record.owner_user_id != user.user_id:
        raise NotFoundAPIError("Grounded summary was not found.")
    return _summary_result(record)
