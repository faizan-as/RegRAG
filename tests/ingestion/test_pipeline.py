"""Tests for ingestion orchestration and reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import src.ingestion.pipeline as pipeline
from src.common.storage import LocalArtifactStore
from src.db.models import SourceArtifact
from src.ingestion.fda_catalog import CatalogSyncResult
from src.ingestion.indexer import IndexingOutcome
from src.ingestion.pipeline import (
    process_tier2_changes,
    reconcile_index_counts,
    run_daily_ingestion,
    schedule_daily_ingestion,
)
from src.ingestion.registry import RegistryChange, RegistryChangeType


async def test_process_tier2_changes_preserves_order_and_logs_outcomes() -> None:
    changes = [
        RegistryChange(slug="a", change_type=RegistryChangeType.NEW),
        RegistryChange(slug="b", change_type=RegistryChangeType.WITHDRAWN),
    ]
    logged = []

    async def processor(change: RegistryChange) -> IndexingOutcome | None:
        if change.slug == "b":
            return None
        return _outcome(change.slug)

    outcomes = await process_tier2_changes(
        changes,
        processor=processor,
        max_concurrency=2,
        outcome_logger=logged.append,
    )

    assert [outcome.document_slug for outcome in outcomes] == ["a"]
    assert logged == outcomes


async def test_process_tier2_changes_rejects_invalid_concurrency() -> None:
    async def processor(change: RegistryChange) -> None:
        del change

    with pytest.raises(ValueError, match="max_concurrency"):
        await process_tier2_changes([], processor=processor, max_concurrency=0)


async def test_process_tier2_changes_retries_with_backoff() -> None:
    change = RegistryChange(slug="retry-guidance", change_type=RegistryChangeType.UPDATED)
    attempts = 0
    sleeps = []

    async def processor(change: RegistryChange) -> IndexingOutcome:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary failure")
        return _outcome(change.slug)

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    outcomes = await process_tier2_changes(
        [change],
        processor=processor,
        retry_attempts=2,
        backoff_seconds=0.5,
        sleep=sleep,
    )

    assert attempts == 2
    assert sleeps == [0.5]
    assert outcomes[0].document_slug == "retry-guidance"


async def test_run_daily_ingestion_writes_report(monkeypatch, tmp_path: Path) -> None:
    generated_at = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    changes = [RegistryChange(slug="new-guidance", change_type=RegistryChangeType.NEW)]

    async def fake_sync_fda_catalog(session, *, data, retrieved_at, store):
        del session, data, retrieved_at, store
        return CatalogSyncResult(
            artifact=_artifact(),
            record_count=1,
            change_count=1,
            changes=changes,
        )

    async def processor(change: RegistryChange) -> IndexingOutcome:
        return _outcome(change.slug, synced_at=generated_at)

    monkeypatch.setattr(pipeline, "sync_fda_catalog", fake_sync_fda_catalog)
    store = LocalArtifactStore(tmp_path)

    result = await run_daily_ingestion(
        _FakeSession(),
        tier2_processor=processor,
        catalog_data=b"[]",
        retrieved_at=generated_at,
        store=store,
    )

    assert result.catalog.change_count == 1
    assert result.indexing_outcomes[0].document_slug == "new-guidance"
    assert result.report_artifact.object_key == "reports/daily-updates/2026-07-22.json"
    assert store.exists(result.report_artifact.object_key)


async def test_reconcile_index_counts_uses_dense_and_keyword_counts() -> None:
    session = _FakeSession(scalars=[2, 2])
    keyword_client = _FakeKeywordClient(count=2)

    result = await reconcile_index_counts(
        session,
        keyword_client=keyword_client,
        index_name="fda_guidance",
    )

    assert result.active_registry_count == 2
    assert result.dense_indexed_document_count == 2
    assert result.keyword_indexed_document_count == 2
    assert result.is_consistent is True
    assert keyword_client.search_calls[0]["index"] == "fda_guidance"


def test_schedule_daily_ingestion_adds_cron_job() -> None:
    scheduler = _FakeScheduler()

    job = schedule_daily_ingestion(scheduler, lambda: None, cron="0 2 * * *")

    assert job == "job-id"
    assert scheduler.calls[0]["id"] == "daily_fda_ingestion"
    assert scheduler.calls[0]["replace_existing"] is True


def _artifact() -> SourceArtifact:
    return SourceArtifact(
        storage_backend="local",
        object_key="catalog/search-for-guidance/sample.json",
        artifact_kind="catalog_snapshot",
        content_type="application/json",
        sha256="a" * 64,
        size_bytes=2,
        source_url="https://www.fda.gov/files/api/datatables/static/search-for-guidance.json",
    )


def _outcome(slug: str, *, synced_at: datetime | None = None) -> IndexingOutcome:
    return IndexingOutcome(
        document_slug=slug,
        version_hash="a" * 64,
        dense_deleted=0,
        keyword_deleted=0,
        dense_indexed=1,
        keyword_indexed=1,
        synced_at=synced_at or datetime(2026, 7, 22, tzinfo=UTC),
    )


class _FakeSession:
    def __init__(self, *, scalars: list[int] | None = None) -> None:
        self.scalars = scalars or []

    async def execute(self, statement):
        del statement
        return _FakeResult(self.scalars.pop(0))


class _FakeResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class _FakeKeywordClient:
    def __init__(self, *, count: int) -> None:
        self.count = count
        self.search_calls = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return {"aggregations": {"documents": {"value": self.count}}}


class _FakeScheduler:
    def __init__(self) -> None:
        self.calls = []

    def add_job(self, job, *, trigger, id, replace_existing):
        self.calls.append(
            {"job": job, "trigger": trigger, "id": id, "replace_existing": replace_existing}
        )
        return "job-id"