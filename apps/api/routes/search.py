"""Hybrid retrieval API route."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.audit import record_audit_event
from apps.api.deps import get_db_session, get_resources
from apps.api.errors import RetrievalUnavailableError, ValidationAPIError
from apps.api.ratelimit import enforce_search_rate_limit
from apps.api.resources import AppResources
from apps.api.schemas.common import TransparencyMetadata
from apps.api.schemas.search import SearchRequest, SearchResponse
from apps.api.security import AuthenticatedUser, require_roles
from src.retrieval.client import RetrievalError, hybrid_search
from src.retrieval.filters import RetrievalFilters

router = APIRouter(prefix="/api/search", tags=["search"])


def normalize_filters(raw_filters: dict[str, Any]) -> tuple[RetrievalFilters, list[str]]:
    """Validate known public filters and report unknown keys."""
    allowed = set(RetrievalFilters.model_fields)
    known = {key: value for key, value in raw_filters.items() if key in allowed}
    ignored = sorted(key for key in raw_filters if key not in allowed)
    for field_name in {"topics", "cfr_references", "product_codes"}:
        value = known.get(field_name)
        if isinstance(value, str):
            known[field_name] = [item.strip() for item in value.split(",") if item.strip()]
    try:
        return RetrievalFilters.model_validate(known), ignored
    except ValidationError as exc:
        details = [dict(error) for error in exc.errors()]
        raise ValidationAPIError("Invalid retrieval filters.", details=details) from exc


@router.post("", response_model=SearchResponse, dependencies=[Depends(enforce_search_rate_limit)])
async def search(
    payload: SearchRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    resources: AppResources = Depends(get_resources),
    user: AuthenticatedUser = Depends(require_roles("researcher", "admin")),
) -> SearchResponse:
    """Return hybrid retrieval evidence without generating an answer."""
    filters, ignored = normalize_filters(payload.filters)
    try:
        result = await hybrid_search(
            payload.query,
            session=session,
            opensearch_client=resources.opensearch_client,
            embedding_model=resources.embedding_model,
            reranker_model=resources.reranker_model,
            filters=filters,
            top_k=payload.top_k,
            rerank_top_k=payload.rerank_top_k,
        )
    except RetrievalError as exc:
        await record_audit_event(
            session,
            event_type="search_failed",
            user_id=user.user_id,
            session_id=None,
            route="/api/search",
            request_id=request.state.request_id,
            payload={"diagnostic_codes": exc.diagnostic_codes},
        )
        raise RetrievalUnavailableError("Retrieval is currently unavailable.") from exc

    diagnostics = {
        "dense_status": result.dense_status.value,
        "keyword_status": result.keyword_status.value,
        "reranker_status": result.reranker_status.value,
        "codes": [
            code
            for code in (result.dense_error, result.keyword_error, result.reranker_error)
            if code
        ],
    }
    await record_audit_event(
        session,
        event_type="search_completed",
        user_id=user.user_id,
        session_id=None,
        route="/api/search",
        request_id=request.state.request_id,
        payload={
            "filters": filters.model_dump(mode="json", exclude_none=True),
            "ignored_filter_keys": ignored,
            "result_count": len(result.search_results),
            "diagnostics": diagnostics,
        },
    )
    return SearchResponse(
        results=result.search_results,
        evidence=result.evidence_cards,
        transparency=TransparencyMetadata(
            retrieval_diagnostics=diagnostics,
            ignored_filter_keys=ignored,
        ),
    )
