"""PostgreSQL registry upsert and change detection for FDA catalog sync."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import GuidanceRegistry, LifecycleState
from src.ingestion.fda_catalog import NormalizedCatalogRecord


UPSERT_BATCH_SIZE = 500


class RegistryChangeType(str, Enum):
    """Catalog change types emitted by Tier 1 sync."""

    NEW = "new"
    UPDATED = "updated"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class RegistryChange:
    """A registry-level catalog change used to trigger downstream ingestion."""

    slug: str
    change_type: RegistryChangeType
    previous_status: str | None = None
    current_status: str | None = None
    previous_fda_last_changed: datetime | None = None
    current_fda_last_changed: datetime | None = None


def diff_catalog_records(
    records: Iterable[NormalizedCatalogRecord],
    existing_records: Mapping[str, GuidanceRegistry],
) -> list[RegistryChange]:
    """Compare incoming catalog records with existing registry rows."""
    incoming_by_slug = {record.slug: record for record in records}
    changes: list[RegistryChange] = []

    for slug, record in incoming_by_slug.items():
        existing = existing_records.get(slug)
        if existing is None:
            changes.append(
                RegistryChange(
                    slug=slug,
                    change_type=RegistryChangeType.NEW,
                    current_status=record.status,
                    current_fda_last_changed=record.fda_last_changed,
                )
            )
            continue

        if _is_updated(record, existing):
            changes.append(
                RegistryChange(
                    slug=slug,
                    change_type=RegistryChangeType.UPDATED,
                    previous_status=existing.status,
                    current_status=record.status,
                    previous_fda_last_changed=existing.fda_last_changed,
                    current_fda_last_changed=record.fda_last_changed,
                )
            )

    for slug, existing in existing_records.items():
        if slug not in incoming_by_slug and existing.lifecycle_state == LifecycleState.ACTIVE:
            changes.append(
                RegistryChange(
                    slug=slug,
                    change_type=RegistryChangeType.WITHDRAWN,
                    previous_status=existing.status,
                    previous_fda_last_changed=existing.fda_last_changed,
                )
            )

    return changes


async def sync_guidance_registry(
    session: AsyncSession,
    records: Iterable[NormalizedCatalogRecord],
    *,
    synced_at: datetime | None = None,
) -> list[RegistryChange]:
    """Upsert normalized catalog records and soft-withdraw absent active rows."""
    record_list = list(records)
    now = synced_at or datetime.now(UTC)
    existing = await load_registry_rows(session)
    changes = diff_catalog_records(record_list, existing)

    if record_list:
        await upsert_registry_records(session, record_list, synced_at=now)

    withdrawn_slugs = [
        change.slug for change in changes if change.change_type == RegistryChangeType.WITHDRAWN
    ]
    for slug in withdrawn_slugs:
        registry_row = existing[slug]
        registry_row.lifecycle_state = LifecycleState.WITHDRAWN
        registry_row.last_seen_at = now
        registry_row.last_synced_at = now
        session.add(registry_row)

    return changes


async def load_registry_rows(session: AsyncSession) -> dict[str, GuidanceRegistry]:
    """Load all current registry rows keyed by slug."""
    result = await session.execute(select(GuidanceRegistry))
    return {row.slug: row for row in result.scalars()}


async def upsert_registry_records(
    session: AsyncSession,
    records: Iterable[NormalizedCatalogRecord],
    *,
    synced_at: datetime,
) -> None:
    """Bulk upsert normalized catalog records into ``guidance_registry``."""
    record_list = list(records)
    for start in range(0, len(record_list), UPSERT_BATCH_SIZE):
        await _upsert_registry_batch(
            session,
            record_list[start : start + UPSERT_BATCH_SIZE],
            synced_at=synced_at,
        )


async def _upsert_registry_batch(
    session: AsyncSession,
    records: list[NormalizedCatalogRecord],
    *,
    synced_at: datetime,
) -> None:
    values = [_registry_values(record, synced_at=synced_at) for record in records]
    if not values:
        return

    statement = insert(GuidanceRegistry).values(values)
    excluded = statement.excluded
    update_columns = {
        "title": excluded.title,
        "landing_url": excluded.landing_url,
        "pdf_url": excluded.pdf_url,
        "status": excluded.status,
        "lifecycle_state": excluded.lifecycle_state,
        "center": excluded.center,
        "communication_type": excluded.communication_type,
        "topics": excluded.topics,
        "regulated_product": excluded.regulated_product,
        "docket_id": excluded.docket_id,
        "docket_url": excluded.docket_url,
        "issue_date": excluded.issue_date,
        "comment_close_date": excluded.comment_close_date,
        "open_comment": excluded.open_comment,
        "fda_last_changed": excluded.fda_last_changed,
        "raw_payload": excluded.raw_payload,
        "last_seen_at": excluded.last_seen_at,
        "last_synced_at": excluded.last_synced_at,
    }
    await session.execute(statement.on_conflict_do_update(index_elements=["slug"], set_=update_columns))


def _registry_values(record: NormalizedCatalogRecord, *, synced_at: datetime) -> dict[str, object]:
    return {
        "slug": record.slug,
        "title": record.title,
        "landing_url": record.landing_url,
        "pdf_url": record.pdf_url,
        "status": record.status,
        "lifecycle_state": LifecycleState.ACTIVE,
        "center": record.center,
        "communication_type": record.communication_type,
        "topics": record.topics,
        "regulated_product": record.regulated_product,
        "docket_id": record.docket_id,
        "docket_url": record.docket_url,
        "issue_date": record.issue_date,
        "comment_close_date": record.comment_close_date,
        "open_comment": record.open_comment,
        "fda_last_changed": record.fda_last_changed,
        "raw_payload": record.raw_payload,
        "last_seen_at": synced_at,
        "last_synced_at": synced_at,
    }


def _is_updated(record: NormalizedCatalogRecord, existing: GuidanceRegistry) -> bool:
    if existing.lifecycle_state == LifecycleState.WITHDRAWN:
        return True
    if existing.status != record.status:
        return True
    if existing.fda_last_changed is None:
        return record.fda_last_changed is not None
    if record.fda_last_changed is None:
        return False
    return record.fda_last_changed > existing.fda_last_changed