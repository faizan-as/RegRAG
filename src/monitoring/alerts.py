"""Update-monitoring alert lifecycle management (create, list, acknowledge, resolve)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AlertRecordORM, AlertStatus
from src.ingestion.registry import RegistryChange


def alert_event_fingerprint(
    change: RegistryChange,
    *,
    current_version_hash: str | None = None,
) -> str:
    """Return a deterministic fingerprint for one source change event."""
    values = (
        change.change_type.value,
        change.slug,
        change.previous_status or "",
        change.current_status or "",
        current_version_hash or "",
        change.previous_fda_last_changed.isoformat() if change.previous_fda_last_changed else "",
        change.current_fda_last_changed.isoformat() if change.current_fda_last_changed else "",
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


async def create_alerts_from_changes(
    session: AsyncSession,
    changes: Iterable[RegistryChange],
    *,
    titles_by_slug: dict[str, str] | None = None,
    version_hashes_by_slug: dict[str, str] | None = None,
) -> list[AlertRecordORM]:
    """Create alert records idempotently at the database constraint boundary."""
    titles_by_slug = titles_by_slug or {}
    version_hashes_by_slug = version_hashes_by_slug or {}
    created: list[AlertRecordORM] = []

    for change in changes:
        current_version_hash = version_hashes_by_slug.get(change.slug)
        record_id = uuid4()
        fingerprint = alert_event_fingerprint(change, current_version_hash=current_version_hash)
        inserted_id = await session.scalar(
            insert(AlertRecordORM)
            .values(
                id=record_id,
                event_fingerprint=fingerprint,
                alert_type=change.change_type.value,
                document_slug=change.slug,
                title=titles_by_slug.get(change.slug, change.slug),
                previous_status=change.previous_status,
                current_status=change.current_status,
                current_version_hash=current_version_hash,
                status=AlertStatus.OPEN.value,
            )
            .on_conflict_do_nothing(index_elements=[AlertRecordORM.event_fingerprint])
            .returning(AlertRecordORM.id)
        )
        if inserted_id is not None:
            record = await session.get(AlertRecordORM, inserted_id)
            if record is not None:
                created.append(record)

    if created:
        await session.commit()
    return created


async def list_alerts(
    session: AsyncSession,
    *,
    status: AlertStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AlertRecordORM]:
    """List alert records ordered by most-recently-detected, optionally filtered by status."""
    stmt = (
        select(AlertRecordORM)
        .order_by(AlertRecordORM.detected_at.desc(), AlertRecordORM.id)
        .offset(offset)
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(AlertRecordORM.status == status.value)
    result = await session.scalars(stmt)
    return list(result)


async def update_alert_status(
    session: AsyncSession,
    alert_id: UUID,
    *,
    status: AlertStatus,
    acknowledged_by: str | None = None,
) -> AlertRecordORM | None:
    """Apply a forward-only alert lifecycle transition without committing."""
    record = await session.get(AlertRecordORM, alert_id)
    if record is None:
        return None

    transitions = {
        AlertStatus.OPEN: {AlertStatus.ACKNOWLEDGED, AlertStatus.RESOLVED},
        AlertStatus.ACKNOWLEDGED: {AlertStatus.RESOLVED},
        AlertStatus.RESOLVED: set(),
    }
    current = AlertStatus(record.status)
    if status == current:
        return record
    if status not in transitions[current]:
        raise ValueError(f"Invalid alert transition: {current.value} -> {status.value}")

    record.status = status.value
    if status == AlertStatus.ACKNOWLEDGED:
        record.acknowledged_by = acknowledged_by
        record.acknowledged_at = datetime.now(UTC)
    elif status == AlertStatus.RESOLVED:
        record.resolved_at = datetime.now(UTC)

    await session.flush()
    return record
