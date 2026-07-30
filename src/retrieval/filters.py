"""Shared metadata filters for PostgreSQL and OpenSearch retrieval."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, cast
from sqlalchemy.sql.elements import ColumnElement

from apps.api.schemas.documents import DocumentStatus
from src.db.models import GuidanceChunk, GuidanceRegistry, LifecycleState


class RetrievalFilters(BaseModel):
    """Metadata filters shared by dense and BM25 retrieval."""

    model_config = ConfigDict(extra="forbid")

    center: str | None = None
    status: DocumentStatus | str | None = None
    lifecycle_state: LifecycleState | str | None = None
    docket_id: str | None = None
    topics: list[str] = Field(default_factory=list)
    communication_type: str | None = None
    regulated_product: str | None = None
    issue_date_from: date | None = None
    issue_date_to: date | None = None
    section_id: str | None = None
    cfr_references: list[str] = Field(default_factory=list)
    product_codes: list[str] = Field(default_factory=list)


def build_postgres_filter_clauses(
    filters: RetrievalFilters | None = None,
) -> list[ColumnElement[bool]]:
    """Build SQLAlchemy WHERE clauses for dense retrieval."""
    filters = filters or RetrievalFilters()
    clauses: list[ColumnElement[bool]] = []

    lifecycle_state = _enum_value(filters.lifecycle_state) or LifecycleState.ACTIVE.value
    clauses.append(GuidanceRegistry.lifecycle_state == lifecycle_state)

    if filters.center:
        clauses.append(GuidanceRegistry.center == filters.center)
    if filters.status:
        clauses.append(GuidanceRegistry.status == _enum_value(filters.status))
    if filters.docket_id:
        clauses.append(GuidanceRegistry.docket_id == filters.docket_id)
    if filters.topics:
        clauses.append(GuidanceRegistry.topics.contains(filters.topics))
    if filters.communication_type:
        clauses.append(GuidanceRegistry.communication_type == filters.communication_type)
    if filters.regulated_product:
        clauses.append(GuidanceRegistry.regulated_product == filters.regulated_product)
    if filters.issue_date_from:
        clauses.append(GuidanceRegistry.issue_date >= filters.issue_date_from)
    if filters.issue_date_to:
        clauses.append(GuidanceRegistry.issue_date <= filters.issue_date_to)
    if filters.section_id:
        clauses.append(GuidanceChunk.section_id == filters.section_id)
    if filters.cfr_references:
        clauses.append(GuidanceChunk.evidence_payload["cfr_references"].contains(filters.cfr_references))
    if filters.product_codes:
        clauses.append(GuidanceChunk.evidence_payload["product_codes"].contains(filters.product_codes))

    return clauses


def build_opensearch_filter_clauses(filters: RetrievalFilters | None = None) -> list[dict[str, Any]]:
    """Build OpenSearch bool filter clauses for BM25 retrieval."""
    filters = filters or RetrievalFilters()
    clauses: list[dict[str, Any]] = []

    lifecycle_state = _enum_value(filters.lifecycle_state) or LifecycleState.ACTIVE.value
    clauses.append({"term": {"lifecycle_state": lifecycle_state}})

    _add_term(clauses, "center", filters.center)
    _add_term(clauses, "status", _enum_value(filters.status))
    _add_term(clauses, "docket_id", filters.docket_id)
    _add_term(clauses, "comm_type", filters.communication_type)
    _add_term(clauses, "regulated_product", filters.regulated_product)
    _add_term(clauses, "section_id", filters.section_id)
    if filters.topics:
        clauses.append({"terms": {"topics": filters.topics}})
    if filters.cfr_references:
        clauses.append({"terms": {"cfr_references": filters.cfr_references}})
    if filters.product_codes:
        clauses.append({"terms": {"product_codes": filters.product_codes}})
    if filters.issue_date_from or filters.issue_date_to:
        issue_date_range: dict[str, str] = {}
        if filters.issue_date_from:
            issue_date_range["gte"] = filters.issue_date_from.isoformat()
        if filters.issue_date_to:
            issue_date_range["lte"] = filters.issue_date_to.isoformat()
        clauses.append({"range": {"issue_date": issue_date_range}})

    return clauses


def evidence_issue_date_expression() -> ColumnElement[date]:
    """Return a cast JSONB issue-date expression for optional dense payload filters."""
    return cast(GuidanceChunk.evidence_payload["issue_date"].astext, Date)


def _enum_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _add_term(clauses: list[dict[str, Any]], field: str, value: Any) -> None:
    if value is not None:
        clauses.append({"term": {field: value}})