"""Ingestion orchestration for catalog sync, Tier 2 indexing, and reporting."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.settings import get_settings
from src.common.storage import ArtifactWriteResult, LocalArtifactStore
from src.db.models import GuidanceChunk, GuidanceRegistry, LifecycleState
from src.ingestion.fda_catalog import CatalogSyncResult, sync_fda_catalog
from src.ingestion.indexer import IndexingOutcome
from src.ingestion.registry import RegistryChange
from src.ingestion.report import DailyUpdateReport, build_daily_update_report, write_daily_update_report


Tier2ChangeProcessor = Callable[[RegistryChange], Awaitable[IndexingOutcome | None]]
OutcomeLogger = Callable[[IndexingOutcome], None]
SleepCallable = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class IngestionRunResult:
    """Result of one orchestrated ingestion run."""

    catalog: CatalogSyncResult
    indexing_outcomes: list[IndexingOutcome]
    report: DailyUpdateReport
    report_artifact: ArtifactWriteResult


@dataclass(frozen=True)
class ReconciliationResult:
    """Nightly reconciliation between registry and retrieval indexes."""

    active_registry_count: int
    dense_indexed_document_count: int
    keyword_indexed_document_count: int | None

    @property
    def is_consistent(self) -> bool:
        """Return whether active registry and index document counts agree."""
        counts = [self.active_registry_count, self.dense_indexed_document_count]
        if self.keyword_indexed_document_count is not None:
            counts.append(self.keyword_indexed_document_count)
        return len(set(counts)) == 1


async def run_daily_ingestion(
    session: AsyncSession,
    *,
    tier2_processor: Tier2ChangeProcessor,
    catalog_data: bytes | None = None,
    retrieved_at: datetime | None = None,
    store: LocalArtifactStore | None = None,
    max_concurrency: int = 4,
    outcome_logger: OutcomeLogger | None = None,
) -> IngestionRunResult:
    """Run Tier 1 catalog sync, Tier 2 change processing, and daily report writing."""
    timestamp = retrieved_at or datetime.now(UTC)
    catalog = await sync_fda_catalog(session, data=catalog_data, retrieved_at=timestamp, store=store)
    outcomes = await process_tier2_changes(
        catalog.changes,
        processor=tier2_processor,
        max_concurrency=max_concurrency,
        outcome_logger=outcome_logger,
    )
    report = build_daily_update_report(
        catalog.changes,
        indexing_outcomes=outcomes,
        generated_at=timestamp,
    )
    report_artifact = write_daily_update_report(report, store=store)
    return IngestionRunResult(
        catalog=catalog,
        indexing_outcomes=outcomes,
        report=report,
        report_artifact=report_artifact,
    )


async def process_tier2_changes(
    changes: Sequence[RegistryChange],
    *,
    processor: Tier2ChangeProcessor,
    max_concurrency: int = 4,
    retry_attempts: int = 3,
    backoff_seconds: float = 1.0,
    sleep: SleepCallable = asyncio.sleep,
    outcome_logger: OutcomeLogger | None = None,
) -> list[IndexingOutcome]:
    """Process Tier 2 changes with bounded concurrency and per-document logging."""
    if max_concurrency <= 0:
        raise ValueError("max_concurrency must be greater than 0")
    if retry_attempts <= 0:
        raise ValueError("retry_attempts must be greater than 0")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be greater than or equal to 0")

    semaphore = asyncio.Semaphore(max_concurrency)

    async def run_one(change: RegistryChange) -> IndexingOutcome | None:
        async with semaphore:
            outcome = await _with_backoff(
                lambda: processor(change),
                attempts=retry_attempts,
                backoff_seconds=backoff_seconds,
                sleep=sleep,
            )
            if outcome is not None and outcome_logger is not None:
                outcome_logger(outcome)
            return outcome

    results = await asyncio.gather(*(run_one(change) for change in changes))
    return [result for result in results if result is not None]


async def _with_backoff(
    operation: Callable[[], Awaitable[IndexingOutcome | None]],
    *,
    attempts: int,
    backoff_seconds: float,
    sleep: SleepCallable,
) -> IndexingOutcome | None:
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception:
            if attempt == attempts:
                raise
            await sleep(backoff_seconds * (2 ** (attempt - 1)))
    return None


async def reconcile_index_counts(
    session: AsyncSession,
    *,
    keyword_client: Any | None = None,
    index_name: str | None = None,
) -> ReconciliationResult:
    """Compare active registry documents with dense and optional keyword index counts."""
    active_registry_count = await _scalar_int(
        session,
        select(func.count()).select_from(GuidanceRegistry).where(
            GuidanceRegistry.lifecycle_state == LifecycleState.ACTIVE
        ),
    )
    dense_indexed_document_count = await _scalar_int(
        session,
        select(func.count(distinct(GuidanceChunk.document_slug))).where(
            GuidanceChunk.document_slug.is_not(None)
        ),
    )
    keyword_count = None
    if keyword_client is not None and index_name is not None:
        response = keyword_client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {"documents": {"cardinality": {"field": "slug"}}},
            },
        )
        keyword_count = int(response["aggregations"]["documents"]["value"])
    return ReconciliationResult(
        active_registry_count=active_registry_count,
        dense_indexed_document_count=dense_indexed_document_count,
        keyword_indexed_document_count=keyword_count,
    )


def schedule_daily_ingestion(scheduler: Any, job: Callable[[], Any], *, cron: str | None = None) -> Any:
    """Schedule the daily ingestion job with APScheduler using a cron expression."""
    from apscheduler.triggers.cron import CronTrigger

    settings = get_settings()
    trigger = CronTrigger.from_crontab(cron or settings.ingest_schedule_cron)
    return scheduler.add_job(job, trigger=trigger, id="daily_fda_ingestion", replace_existing=True)


async def _scalar_int(session: AsyncSession, statement: Any) -> int:
    result = await session.execute(statement)
    return int(result.scalar_one() or 0)