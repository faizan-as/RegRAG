"""Seed a small, real FDA guidance corpus for local end-to-end development."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from apps.api.local_runtime import LocalEmbeddingModel
from apps.api.settings import get_settings
from src.common.clients import get_opensearch_client
from src.common.db import get_session
from src.common.storage import get_artifact_store
from src.db.models import GuidanceRegistry
from src.ingestion.chunking import chunk_parsed_pdf
from src.ingestion.content_acquisition import acquire_guidance_content
from src.ingestion.embedder import embed_chunks
from src.ingestion.fda_catalog import sync_fda_catalog
from src.ingestion.indexer import reindex_changed_document
from src.ingestion.pdf_parser import parse_pdf_bytes

DEFAULT_CATALOG_PATH = Path("Docs/search-for-guidance-sample.json")


@dataclass(frozen=True)
class LocalSeedResult:
    """Counts produced by a local seed run."""

    documents: int
    chunks: int


def directly_downloadable_rows(catalog_data: bytes, *, limit: int) -> bytes:
    """Return at most ``limit`` catalog rows that provide a direct FDA PDF."""
    payload = json.loads(catalog_data)
    if not isinstance(payload, list):
        raise ValueError("Local seed catalog must be a JSON array")
    rows = [row for row in payload if row.get("field_associated_media_2")][:limit]
    if not rows:
        raise ValueError("Local seed catalog does not contain a directly downloadable FDA PDF")
    return json.dumps(rows).encode("utf-8")


async def seed_local_corpus(*, catalog_path: Path, limit: int = 1) -> LocalSeedResult:
    """Acquire and index a bounded set of real FDA guidance PDFs."""
    settings = get_settings()
    if not settings.local_demo_mode:
        raise RuntimeError("Set LOCAL_DEMO_MODE=true before running the local corpus seed")
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    catalog_data = directly_downloadable_rows(catalog_path.read_bytes(), limit=limit)
    store = get_artifact_store()
    opensearch_client = get_opensearch_client()
    embedding_model = LocalEmbeddingModel(settings.embedding_dim)
    indexed_chunks = 0

    async with get_session() as session:
        catalog_result = await sync_fda_catalog(session, data=catalog_data, store=store)
        slugs = [change.slug for change in catalog_result.changes]
        if not slugs:
            payload = json.loads(catalog_data)
            title = str(payload[0]["title"])
            result = await session.execute(
                select(GuidanceRegistry.slug).where(
                    GuidanceRegistry.raw_payload["title"].astext == title
                )
            )
            slugs = list(result.scalars())

        documents = list(
            await session.scalars(select(GuidanceRegistry).where(GuidanceRegistry.slug.in_(slugs)))
        )
        for document in documents:
            acquired = await acquire_guidance_content(session, document, store=store)
            source_bytes = store.read_bytes(acquired.raw_object_key)
            parsed = parse_pdf_bytes(
                source_bytes,
                document_id=document.slug,
                version_hash=acquired.version_hash,
                source_url=acquired.source_url,
            )
            chunks = chunk_parsed_pdf(parsed)
            embedded = embed_chunks(
                chunks,
                model=embedding_model,
                model_name="local-demo-feature-hash-v1",
            )
            outcome = await reindex_changed_document(
                session,
                opensearch_client,
                embedded,
                index_name=settings.opensearch_index,
                document_metadata={
                    "document_id": document.slug,
                    "title": document.title,
                    "source_url": acquired.source_url,
                    "status": document.status,
                    "version_hash": acquired.version_hash,
                    "docket_number": document.docket_id,
                    "center": document.center,
                    "communication_type": document.communication_type,
                    "topics": document.topics,
                    "issue_date": document.issue_date,
                    "lifecycle_state": document.lifecycle_state,
                },
            )
            indexed_chunks += outcome.dense_indexed

    opensearch_client.indices.refresh(index=settings.opensearch_index)
    return LocalSeedResult(documents=len(documents), chunks=indexed_chunks)


def build_parser() -> argparse.ArgumentParser:
    """Build the local seed CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-path", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--limit", type=int, default=1)
    return parser


async def async_main(argv: list[str] | None = None) -> int:
    """Run the asynchronous seed command."""
    args = build_parser().parse_args(argv)
    result = await seed_local_corpus(catalog_path=args.catalog_path, limit=args.limit)
    print(f"local_seed_complete documents={result.documents} chunks={result.chunks}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the local seed command."""
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
