"""Daily update-monitoring alert scan scheduling.

Alerts are derived from the same :class:`RegistryChange` events produced by
Tier 1 catalog sync during daily ingestion (see ``src.ingestion.pipeline``
and ``src.ingestion.registry``). This module wires that change list to
alert-record creation and exposes an APScheduler hook mirroring
``schedule_daily_ingestion``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from src.db.models import AlertRecordORM
from src.ingestion.registry import RegistryChange
from src.monitoring.alerts import create_alerts_from_changes

AlertScanJob = Callable[[], Awaitable[list[AlertRecordORM]]]


def build_alert_scan_job(
    session_factory: Callable[[], Any],
    change_provider: Callable[[], Awaitable[list[RegistryChange]]],
    *,
    titles_by_slug_provider: Callable[[], dict[str, str]] | None = None,
    version_hashes_by_slug_provider: Callable[[], dict[str, str]] | None = None,
) -> AlertScanJob:
    """Build an idempotent async job that creates alert records from the latest registry changes."""

    async def job() -> list[AlertRecordORM]:
        changes = await change_provider()
        session = session_factory()
        try:
            return await create_alerts_from_changes(
                session,
                changes,
                titles_by_slug=titles_by_slug_provider() if titles_by_slug_provider else None,
                version_hashes_by_slug=(
                    version_hashes_by_slug_provider() if version_hashes_by_slug_provider else None
                ),
            )
        finally:
            await session.close()

    return job


def schedule_daily_alert_scan(scheduler: Any, job: AlertScanJob, *, cron: str | None = None) -> Any:
    """Schedule the daily alert scan job with APScheduler using a cron expression."""
    from apscheduler.triggers.cron import CronTrigger

    from apps.api.settings import get_settings

    settings = get_settings()
    trigger = CronTrigger.from_crontab(cron or settings.ingest_schedule_cron)
    return scheduler.add_job(job, trigger=trigger, id="daily_alert_scan", replace_existing=True)
