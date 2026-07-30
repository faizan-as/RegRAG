"""Daily ingestion update reports for FDA guidance changes."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from src.common.storage import ArtifactWriteResult, LocalArtifactStore, get_artifact_store
from src.ingestion.indexer import IndexingOutcome
from src.ingestion.registry import RegistryChange, RegistryChangeType


@dataclass(frozen=True)
class DailyUpdateReport:
    """Daily summary of catalog changes and indexing outcomes."""

    report_date: str
    generated_at: datetime
    total_changes: int
    new_count: int
    updated_count: int
    withdrawn_count: int
    changes: list[dict[str, Any]]
    indexing_outcomes: list[dict[str, Any]]


def build_daily_update_report(
    changes: Sequence[RegistryChange],
    *,
    indexing_outcomes: Sequence[IndexingOutcome] = (),
    generated_at: datetime | None = None,
) -> DailyUpdateReport:
    """Build a serializable daily update report from registry changes."""
    timestamp = generated_at or datetime.now(UTC)
    counts = Counter(change.change_type for change in changes)
    return DailyUpdateReport(
        report_date=timestamp.date().isoformat(),
        generated_at=timestamp,
        total_changes=len(changes),
        new_count=counts[RegistryChangeType.NEW],
        updated_count=counts[RegistryChangeType.UPDATED],
        withdrawn_count=counts[RegistryChangeType.WITHDRAWN],
        changes=[_registry_change_payload(change) for change in changes],
        indexing_outcomes=[_indexing_outcome_payload(outcome) for outcome in indexing_outcomes],
    )


def write_daily_update_report(
    report: DailyUpdateReport,
    *,
    store: LocalArtifactStore | None = None,
) -> ArtifactWriteResult:
    """Write a daily update report JSON artifact to local storage."""
    object_key = PurePosixPath(
        "reports",
        "daily-updates",
        f"{report.report_date}.json",
    ).as_posix()
    payload = json.dumps(_json_safe(asdict(report)), indent=2, sort_keys=True).encode("utf-8")
    artifact_store = store or get_artifact_store()
    return artifact_store.put_bytes(object_key, payload, content_type="application/json")


def _registry_change_payload(change: RegistryChange) -> dict[str, Any]:
    return {
        "slug": change.slug,
        "change_type": change.change_type.value,
        "previous_status": change.previous_status,
        "current_status": change.current_status,
        "previous_fda_last_changed": _json_safe(change.previous_fda_last_changed),
        "current_fda_last_changed": _json_safe(change.current_fda_last_changed),
    }


def _indexing_outcome_payload(outcome: IndexingOutcome) -> dict[str, Any]:
    return {
        "document_slug": outcome.document_slug,
        "version_hash": outcome.version_hash,
        "dense_deleted": outcome.dense_deleted,
        "keyword_deleted": outcome.keyword_deleted,
        "dense_indexed": outcome.dense_indexed,
        "keyword_indexed": outcome.keyword_indexed,
        "synced_at": _json_safe(outcome.synced_at),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value