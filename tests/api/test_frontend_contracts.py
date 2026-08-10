"""Regression tests for API contracts consumed by the Phase 5B frontend."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.api.errors import NotFoundAPIError
from apps.api.main import create_app
from apps.api.routes.search import normalize_filters
from apps.api.routes.sessions import list_sessions
from apps.api.routes.summaries import get_summary
from apps.api.schemas.documents import DocumentStatus
from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.search import SearchFilters
from apps.api.security import AuthenticatedUser


def _evidence_payload() -> dict[str, object]:
    return EvidenceCard(
        citation_id="[1]",
        document_id="guidance-1",
        chunk_id="guidance-1:version:chunk-1",
        title="FDA Guidance",
        passage="Grounded FDA passage.",
        source_url="https://www.fda.gov/example",
        version_hash="a" * 64,
        document_status=DocumentStatus.FINAL,
        retrieval_score=0.8,
        rerank_score=0.9,
        confidence=0.9,
    ).model_dump(mode="json")


def test_openapi_exposes_frontend_contracts_without_storage_keys() -> None:
    specification = create_app().openapi()
    schemas = specification["components"]["schemas"]
    paths = specification["paths"]

    assert "get" in paths["/api/sessions"]
    assert "get" in paths["/api/summaries/{summary_id}"]
    assert "raw_object_key" not in schemas["GuidanceDocument"]["properties"]
    assert "raw_object_key" not in schemas["DocumentVersionResponse"]["properties"]
    assert "artifacts" in schemas["GuidanceDocument"]["properties"]
    assert "chunk_id" in schemas["EvidenceCard"]["required"]
    assert "offset" in schemas["AlertListResponse"]["required"]
    assert "SearchFilters" in schemas
    assert "ErrorResponse" in schemas
    assert "ChatStreamEvent" in schemas

    stream_content = paths["/api/chat/stream"]["post"]["responses"]["200"]["content"]
    assert "text/event-stream" in stream_content
    validation_schema = paths["/api/search"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]
    assert validation_schema["$ref"].endswith("/ErrorResponse")


def test_typed_search_filters_preserve_known_values_and_report_extras() -> None:
    filters, ignored = normalize_filters(
        SearchFilters(
            topics=["Drug Safety"],
            issue_date_from=date(2025, 1, 1),
            future_filter="ignored-for-now",
        )
    )

    assert filters.topics == ["Drug Safety"]
    assert filters.issue_date_from == date(2025, 1, 1)
    assert ignored == ["future_filter"]


class _SessionPage:
    def __init__(self, records: list[SimpleNamespace]) -> None:
        self.records = records
        self.statement = None

    async def scalars(self, statement):
        self.statement = statement
        return self.records


async def test_session_list_is_owner_filtered_and_paginated() -> None:
    now = datetime.now(UTC)
    database = _SessionPage(
        [SimpleNamespace(id="session-1", title="Research", status="active", created_at=now)]
    )

    result = await list_sessions(
        limit=10,
        offset=20,
        session=database,
        user=AuthenticatedUser(user_id="user-1"),
    )

    assert result.limit == 10
    assert result.offset == 20
    assert result.sessions[0].session_id == "session-1"
    compiled = str(database.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "chat_sessions.owner_user_id = 'user-1'" in compiled
    assert "LIMIT 10 OFFSET 20" in compiled


class _SummaryLookup:
    def __init__(self, record: SimpleNamespace) -> None:
        self.record = record

    async def get(self, model, record_id):
        return self.record


async def test_summary_read_reconstructs_owned_record_and_hides_other_users() -> None:
    summary_id = uuid4()
    record = SimpleNamespace(
        id=summary_id,
        owner_user_id="user-1",
        document_slug="guidance-1",
        summary_type="summary",
        text="Grounded summary [1].",
        evidence=[_evidence_payload()],
        refused=False,
        refusal_reason=None,
        current_version_hash="a" * 64,
        previous_version_hash=None,
        guardrail_metadata={"faithfulness_passed": True},
        created_at=datetime.now(UTC),
    )
    database = _SummaryLookup(record)

    result = await get_summary(
        summary_id=summary_id,
        db=database,
        user=AuthenticatedUser(user_id="user-1"),
    )
    assert result.summary_id == str(summary_id)
    assert result.evidence[0].chunk_id == "guidance-1:version:chunk-1"

    with pytest.raises(NotFoundAPIError):
        await get_summary(
            summary_id=summary_id,
            db=database,
            user=AuthenticatedUser(user_id="user-2"),
        )
