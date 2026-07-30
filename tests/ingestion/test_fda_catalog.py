"""Tests for FDA catalog snapshot and normalization helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.common.storage import LocalArtifactStore
from src.ingestion.fda_catalog import (
    load_catalog_rows,
    normalize_catalog_rows,
    snapshot_catalog_bytes,
    source_artifact_from_write_result,
    sync_fda_catalog,
)


def test_load_and_normalize_sample_catalog() -> None:
    """The FDA sample fixture normalizes into registry-ready rows."""
    data = Path("Docs/search-for-guidance-sample.json").read_bytes()
    rows = load_catalog_rows(data)
    records = normalize_catalog_rows(rows, base_url="https://www.fda.gov")

    assert len(records) == 4
    assert records[0].slug == (
        "small-entity-compliance-guide-safe-handling-statements-labeling-shell-eggs-and-refrigeration-shell"
    )
    assert records[0].title.startswith("Small Entity Compliance Guide")
    assert records[0].landing_url.startswith("https://www.fda.gov/regulatory-information/")
    assert records[0].open_comment is False
    assert records[0].regulated_product == "Food & Beverages"
    assert records[0].docket_id == "FDA-2020-D-1954"
    assert records[2].status == "Draft"
    assert records[2].comment_close_date is not None
    assert records[3].pdf_url == "https://www.fda.gov/media/120958/download"
    assert records[3].topics == ["Bioengineering / GMOs", "Labeling"]
    assert records[3].fda_last_changed is not None


def test_catalog_urls_are_built_from_fda_base_url_and_anchor_hrefs() -> None:
    """FDA catalog URLs come from base URL plus title/media anchor hrefs."""
    data = Path("Docs/search-for-guidance-sample.json").read_bytes()
    rows = load_catalog_rows(data)
    record = normalize_catalog_rows(rows, base_url="https://www.fda.gov")[3]

    assert record.landing_url == (
        "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/"
        "guidance-industry-voluntary-labeling-indicating-whether-foods-have-or-have-not-been-derived"
    )
    assert record.pdf_url == "https://www.fda.gov/media/120958/download"


def test_load_catalog_rows_accepts_concatenated_snapshot_objects() -> None:
    """Full FDA snapshots may be saved as comma-separated objects without an array wrapper."""
    data = b'{"title": "A"},{"title": "B"}]\n'

    rows = load_catalog_rows(data)

    assert rows == [{"title": "A"}, {"title": "B"}]


def test_snapshot_catalog_bytes_and_artifact_metadata(tmp_path: Path) -> None:
    """Catalog snapshots are written under dated keys and mapped to metadata rows."""
    store = LocalArtifactStore(tmp_path)
    data = b"[]"

    result = snapshot_catalog_bytes(
        data,
        retrieved_at=datetime(2026, 7, 20, 18, 15, tzinfo=UTC),
        store=store,
    )
    artifact = source_artifact_from_write_result(
        result,
        artifact_kind="catalog_snapshot",
        source_url="https://www.fda.gov/files/api/datatables/static/search-for-guidance.json",
    )

    assert result.object_key == "catalog/search-for-guidance/20260720T181500Z.json"
    assert store.read_bytes(result.object_key) == data
    assert artifact.storage_backend == "local"
    assert artifact.object_key == result.object_key
    assert artifact.artifact_kind == "catalog_snapshot"
    assert artifact.size_bytes == 2


async def test_sync_fda_catalog_persists_snapshot_metadata_and_syncs_registry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Tier 1 sync stores snapshot metadata and delegates registry synchronization."""
    import src.ingestion.registry as registry_module

    synced_records = []

    async def fake_sync_guidance_registry(session, records, *, synced_at):
        del session, synced_at
        synced_records.extend(records)
        return [object()]

    monkeypatch.setattr(registry_module, "sync_guidance_registry", fake_sync_guidance_registry)
    session = _FakeSession()
    store = LocalArtifactStore(tmp_path)
    data = Path("Docs/search-for-guidance-sample.json").read_bytes()

    result = await sync_fda_catalog(
        session,
        data=data,
        retrieved_at=datetime(2026, 7, 20, 18, 15, tzinfo=UTC),
        store=store,
    )

    assert result.record_count == 4
    assert result.change_count == 1
    assert result.artifact.object_key == "catalog/search-for-guidance/20260720T181500Z.json"
    assert session.added == [result.artifact]
    assert len(synced_records) == 4


class _FakeSession:
    def __init__(self) -> None:
        self.added = []

    def add(self, instance) -> None:
        self.added.append(instance)