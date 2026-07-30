"""Tests for the one-time FDA metadata backfill runner."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from src.ingestion.backfill import format_summary, run_metadata_backfill
from src.ingestion.registry import RegistryChange, RegistryChangeType


async def test_run_metadata_backfill_uses_local_catalog_fixture(monkeypatch, tmp_path: Path) -> None:
    """The backfill runner can use a local catalog file and summarize sync results."""
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(b"[]")
    calls = {}

    async def fake_sync_fda_catalog(session, *, data=None, retrieved_at=None, store=None):
        del retrieved_at, store
        calls["session"] = session
        calls["data"] = data
        return _FakeCatalogSyncResult()

    @asynccontextmanager
    async def fake_session_context():
        yield "session"

    monkeypatch.setattr("src.ingestion.backfill.sync_fda_catalog", fake_sync_fda_catalog)

    summary = await run_metadata_backfill(
        catalog_path=catalog_path,
        session_context_factory=fake_session_context,
    )

    assert calls == {"session": "session", "data": b"[]"}
    assert summary.record_count == 10
    assert summary.change_count == 3
    assert summary.new_count == 1
    assert summary.updated_count == 1
    assert summary.withdrawn_count == 1
    assert "records=10" in format_summary(summary)
    assert "artifact=catalog/search-for-guidance/test.json" in format_summary(summary)


class _FakeArtifact:
    object_key = "catalog/search-for-guidance/test.json"


class _FakeCatalogSyncResult:
    artifact = _FakeArtifact()
    record_count = 10
    change_count = 3
    changes = [
        RegistryChange(slug="new", change_type=RegistryChangeType.NEW),
        RegistryChange(slug="updated", change_type=RegistryChangeType.UPDATED),
        RegistryChange(slug="withdrawn", change_type=RegistryChangeType.WITHDRAWN),
    ]