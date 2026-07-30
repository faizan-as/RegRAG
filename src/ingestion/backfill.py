"""One-time metadata backfill runner for the FDA guidance catalog."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.db import get_session
from src.ingestion.fda_catalog import CatalogSyncResult, sync_fda_catalog
from src.ingestion.registry import RegistryChangeType


SessionContextFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class MetadataBackfillSummary:
    """Console-safe summary for a one-time metadata backfill run."""

    record_count: int
    change_count: int
    new_count: int
    updated_count: int
    withdrawn_count: int
    artifact_object_key: str

    @classmethod
    def from_catalog_sync(cls, result: CatalogSyncResult) -> MetadataBackfillSummary:
        """Build a summary from a catalog sync result."""
        counts = Counter(change.change_type for change in result.changes)
        return cls(
            record_count=result.record_count,
            change_count=result.change_count,
            new_count=counts[RegistryChangeType.NEW],
            updated_count=counts[RegistryChangeType.UPDATED],
            withdrawn_count=counts[RegistryChangeType.WITHDRAWN],
            artifact_object_key=result.artifact.object_key,
        )


async def run_metadata_backfill(
    *,
    catalog_path: Path | None = None,
    session_context_factory: SessionContextFactory = get_session,
) -> MetadataBackfillSummary:
    """Run the Tier 1 metadata backfill without downloading document content."""
    data = catalog_path.read_bytes() if catalog_path is not None else None
    async with session_context_factory() as session:
        result = await sync_fda_catalog(session, data=data)
    return MetadataBackfillSummary.from_catalog_sync(result)


def build_parser() -> argparse.ArgumentParser:
    """Create the metadata backfill CLI parser."""
    parser = argparse.ArgumentParser(
        description="Run Tier 1 FDA guidance metadata backfill without downloading PDFs."
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=None,
        help="Optional local FDA catalog JSON fixture/snapshot. Defaults to the configured live FDA URL.",
    )
    return parser


def format_summary(summary: MetadataBackfillSummary) -> str:
    """Format a compact backfill summary for CLI output."""
    return (
        "metadata_backfill_complete "
        f"records={summary.record_count} "
        f"changes={summary.change_count} "
        f"new={summary.new_count} "
        f"updated={summary.updated_count} "
        f"withdrawn={summary.withdrawn_count} "
        f"artifact={summary.artifact_object_key}"
    )


async def async_main(argv: list[str] | None = None) -> int:
    """Run the async CLI entrypoint."""
    args = build_parser().parse_args(argv)
    summary = await run_metadata_backfill(catalog_path=args.catalog_path)
    print(format_summary(summary))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entrypoint."""
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())