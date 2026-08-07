"""Diff summaries between preserved FDA guidance document versions."""

from __future__ import annotations

import difflib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import GuidanceChunk


async def _parent_chunk_texts(
    session: AsyncSession, document_slug: str, version_hash: str
) -> list[str]:
    stmt = (
        select(GuidanceChunk.text)
        .where(
            GuidanceChunk.document_slug == document_slug,
            GuidanceChunk.version_hash == version_hash,
            GuidanceChunk.chunk_type == "parent",
        )
        .order_by(GuidanceChunk.chunk_id)
    )
    result = await session.scalars(stmt)
    return list(result)


async def diff_document_versions(
    session: AsyncSession,
    document_slug: str,
    *,
    previous_version_hash: str,
    current_version_hash: str,
) -> list[str]:
    """Return unified-diff lines between two preserved versions of a document's parent chunks."""
    previous_texts = await _parent_chunk_texts(session, document_slug, previous_version_hash)
    current_texts = await _parent_chunk_texts(session, document_slug, current_version_hash)
    diff = difflib.unified_diff(
        previous_texts,
        current_texts,
        fromfile=f"{document_slug}@{previous_version_hash[:12]}",
        tofile=f"{document_slug}@{current_version_hash[:12]}",
        lineterm="",
    )
    return list(diff)
