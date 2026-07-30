"""Tests for daily ingestion update reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.common.storage import LocalArtifactStore
from src.ingestion.indexer import IndexingOutcome
from src.ingestion.registry import RegistryChange, RegistryChangeType
from src.ingestion.report import build_daily_update_report, write_daily_update_report


def test_build_daily_update_report_counts_changes_and_outcomes() -> None:
    generated_at = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    changes = [
        RegistryChange(slug="new-guidance", change_type=RegistryChangeType.NEW, current_status="Final"),
        RegistryChange(slug="updated-guidance", change_type=RegistryChangeType.UPDATED),
        RegistryChange(slug="withdrawn-guidance", change_type=RegistryChangeType.WITHDRAWN),
    ]
    outcome = IndexingOutcome(
        document_slug="new-guidance",
        version_hash="a" * 64,
        dense_deleted=0,
        keyword_deleted=0,
        dense_indexed=2,
        keyword_indexed=2,
        synced_at=generated_at,
    )

    report = build_daily_update_report(changes, indexing_outcomes=[outcome], generated_at=generated_at)

    assert report.report_date == "2026-07-22"
    assert report.total_changes == 3
    assert report.new_count == 1
    assert report.updated_count == 1
    assert report.withdrawn_count == 1
    assert report.changes[0]["change_type"] == "new"
    assert report.indexing_outcomes[0]["dense_indexed"] == 2


def test_write_daily_update_report_to_local_artifact_store(tmp_path: Path) -> None:
    generated_at = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    report = build_daily_update_report([], generated_at=generated_at)
    store = LocalArtifactStore(tmp_path)

    artifact = write_daily_update_report(report, store=store)

    assert artifact.object_key == "reports/daily-updates/2026-07-22.json"
    payload = json.loads(store.read_bytes(artifact.object_key))
    assert payload["report_date"] == "2026-07-22"
    assert payload["generated_at"] == "2026-07-22T09:00:00+00:00"