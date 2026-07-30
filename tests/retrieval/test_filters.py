"""Tests for shared retrieval filter builders."""

from __future__ import annotations

from datetime import date

from sqlalchemy.dialects import postgresql

from apps.api.schemas.documents import DocumentStatus
from src.db.models import LifecycleState
from src.retrieval.filters import (
    RetrievalFilters,
    build_opensearch_filter_clauses,
    build_postgres_filter_clauses,
)


def test_postgres_filters_default_to_active_lifecycle() -> None:
    clauses = build_postgres_filter_clauses()

    compiled = _compile_clause(clauses[0])

    assert "guidance_registry.lifecycle_state" in compiled
    assert clauses[0].right.value == LifecycleState.ACTIVE.value


def test_postgres_filters_include_metadata_clauses() -> None:
    filters = RetrievalFilters(
        center="CDER",
        status=DocumentStatus.FINAL,
        docket_id="FDA-2026-D-0001",
        topics=["Clinical"],
        issue_date_from=date(2026, 1, 1),
        issue_date_to=date(2026, 12, 31),
        section_id="i-introduction",
    )

    compiled = "\n".join(_compile_clause(clause) for clause in build_postgres_filter_clauses(filters))

    assert "guidance_registry.center" in compiled
    assert "guidance_registry.status" in compiled
    assert "guidance_registry.docket_id" in compiled
    assert "guidance_registry.topics" in compiled
    assert "guidance_registry.issue_date" in compiled
    assert "guidance_chunks.section_id" in compiled


def test_opensearch_filters_default_to_active_lifecycle() -> None:
    assert build_opensearch_filter_clauses() == [
        {"term": {"lifecycle_state": LifecycleState.ACTIVE.value}}
    ]


def test_opensearch_filters_include_terms_and_date_range() -> None:
    filters = RetrievalFilters(
        center="CDER",
        status=DocumentStatus.DRAFT,
        lifecycle_state=LifecycleState.WITHDRAWN,
        docket_id="FDA-2026-D-0001",
        topics=["Clinical", "Drugs"],
        communication_type="Guidance Document",
        regulated_product="Drugs",
        issue_date_from=date(2026, 1, 1),
        issue_date_to=date(2026, 12, 31),
        section_id="i-introduction",
        cfr_references=["21 CFR 312"],
        product_codes=["ABC"],
    )

    clauses = build_opensearch_filter_clauses(filters)

    assert {"term": {"lifecycle_state": "withdrawn"}} in clauses
    assert {"term": {"center": "CDER"}} in clauses
    assert {"term": {"status": "Draft"}} in clauses
    assert {"term": {"docket_id": "FDA-2026-D-0001"}} in clauses
    assert {"term": {"comm_type": "Guidance Document"}} in clauses
    assert {"term": {"regulated_product": "Drugs"}} in clauses
    assert {"term": {"section_id": "i-introduction"}} in clauses
    assert {"terms": {"topics": ["Clinical", "Drugs"]}} in clauses
    assert {"terms": {"cfr_references": ["21 CFR 312"]}} in clauses
    assert {"terms": {"product_codes": ["ABC"]}} in clauses
    assert {"range": {"issue_date": {"gte": "2026-01-01", "lte": "2026-12-31"}}} in clauses


def _compile_clause(clause) -> str:
    return str(clause.compile(dialect=postgresql.dialect()))