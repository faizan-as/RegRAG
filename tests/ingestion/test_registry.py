"""Tests for FDA guidance registry diff and upsert helpers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects import postgresql

from src.db.models import GuidanceRegistry, LifecycleState
from src.ingestion.fda_catalog import load_catalog_rows, normalize_catalog_rows
from src.ingestion import registry as registry_module
from src.ingestion.registry import (
    RegistryChangeType,
    diff_catalog_records,
    upsert_registry_records,
)


def test_diff_catalog_records_emits_new_updated_and_withdrawn() -> None:
    """Catalog diffs identify new, updated, and absent active registry rows."""
    records = _sample_records()
    existing = {
        records[1].slug: GuidanceRegistry(
            slug=records[1].slug,
            title=records[1].title,
            status=records[1].status,
            lifecycle_state=LifecycleState.ACTIVE,
            fda_last_changed=records[1].fda_last_changed,
            raw_payload={},
            topics=[],
        ),
        records[2].slug: GuidanceRegistry(
            slug=records[2].slug,
            title=records[2].title,
            status="Final",
            lifecycle_state=LifecycleState.ACTIVE,
            fda_last_changed=records[2].fda_last_changed,
            raw_payload={},
            topics=[],
        ),
        "withdrawn-guidance": GuidanceRegistry(
            slug="withdrawn-guidance",
            title="Withdrawn Guidance",
            status="Final",
            lifecycle_state=LifecycleState.ACTIVE,
            raw_payload={},
            topics=[],
        ),
    }

    changes = diff_catalog_records(records[:3], existing)
    changes_by_slug = {change.slug: change for change in changes}

    assert changes_by_slug[records[0].slug].change_type == RegistryChangeType.NEW
    assert changes_by_slug[records[2].slug].change_type == RegistryChangeType.UPDATED
    assert changes_by_slug["withdrawn-guidance"].change_type == RegistryChangeType.WITHDRAWN
    assert records[1].slug not in changes_by_slug


def test_diff_catalog_records_treats_newer_changed_timestamp_as_updated() -> None:
    """A newer FDA changed timestamp emits an UPDATED event."""
    record = _sample_records()[0]
    existing = GuidanceRegistry(
        slug=record.slug,
        title=record.title,
        status=record.status,
        lifecycle_state=LifecycleState.ACTIVE,
        fda_last_changed=datetime.fromisoformat("2024-01-01T00:00:00-04:00"),
        raw_payload={},
        topics=[],
    )

    changes = diff_catalog_records([record], {record.slug: existing})

    assert len(changes) == 1
    assert changes[0].change_type == RegistryChangeType.UPDATED


def test_diff_catalog_records_ignores_already_withdrawn_absent_row() -> None:
    """Previously withdrawn rows are not repeatedly emitted as withdrawn."""
    existing = GuidanceRegistry(
        slug="already-withdrawn",
        title="Already Withdrawn",
        status="Final",
        lifecycle_state=LifecycleState.WITHDRAWN,
        raw_payload={},
        topics=[],
    )

    assert diff_catalog_records([], {existing.slug: existing}) == []


async def test_upsert_registry_records_uses_postgresql_conflict_update() -> None:
    """Registry upsert compiles to PostgreSQL ON CONFLICT for slug idempotency."""
    record = _sample_records()[0]
    session = _FakeSession()

    await upsert_registry_records(
        session,
        [record],
        synced_at=datetime.fromisoformat("2026-07-20T18:15:00+00:00"),
    )

    compiled = session.statement.compile(dialect=postgresql.dialect())

    assert "ON CONFLICT (slug) DO UPDATE" in str(compiled)


async def test_upsert_registry_records_batches_large_catalog(monkeypatch) -> None:
    """Large catalog upserts are split into bounded PostgreSQL batches."""
    records = _sample_records()[:1] * 3
    batch_sizes = []

    async def fake_upsert_registry_batch(session, batch, *, synced_at):
        del session, synced_at
        batch_sizes.append(len(batch))

    monkeypatch.setattr(registry_module, "UPSERT_BATCH_SIZE", 2)
    monkeypatch.setattr(registry_module, "_upsert_registry_batch", fake_upsert_registry_batch)

    await upsert_registry_records(
        _FakeSession(),
        records,
        synced_at=datetime.fromisoformat("2026-07-20T18:15:00+00:00"),
    )

    assert batch_sizes == [2, 1]


def _sample_records():
    data = open("Docs/search-for-guidance-sample.json", "rb").read()
    return normalize_catalog_rows(load_catalog_rows(data), base_url="https://www.fda.gov")


class _FakeSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement