"""Tests for alert fingerprints and lifecycle transitions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.db.models import AlertRecordORM, AlertStatus
from src.ingestion.registry import RegistryChange, RegistryChangeType
from src.monitoring.alerts import alert_event_fingerprint, update_alert_status


def test_alert_fingerprint_is_deterministic_and_version_sensitive() -> None:
    change = RegistryChange(
        slug="guidance",
        change_type=RegistryChangeType.UPDATED,
        previous_status="Draft",
        current_status="Final",
        current_fda_last_changed=datetime(2026, 8, 6, tzinfo=UTC),
    )

    assert alert_event_fingerprint(
        change, current_version_hash="a" * 64
    ) == alert_event_fingerprint(change, current_version_hash="a" * 64)
    assert alert_event_fingerprint(
        change, current_version_hash="a" * 64
    ) != alert_event_fingerprint(change, current_version_hash="b" * 64)


class _FakeSession:
    def __init__(self, record) -> None:
        self.record = record

    async def get(self, model, record_id):
        return self.record

    async def flush(self) -> None:
        return None


async def test_alert_transition_cannot_move_backward() -> None:
    record = AlertRecordORM(
        event_fingerprint="a" * 64,
        alert_type="updated",
        title="Guidance",
        status=AlertStatus.RESOLVED.value,
    )

    with pytest.raises(ValueError, match="resolved -> acknowledged"):
        await update_alert_status(
            _FakeSession(record),
            record.id,
            status=AlertStatus.ACKNOWLEDGED,
            acknowledged_by="admin",
        )
