"""PostgreSQL + pgvector dense retrieval client."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Float, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas.chunks import Chunk, ChunkType
from apps.api.schemas.search import RetrievalSource
from apps.api.settings import get_settings
from src.db.models import GuidanceChunk, GuidanceRegistry
from src.retrieval.filters import RetrievalFilters, build_postgres_filter_clauses
from src.retrieval.models import RetrievalCandidate


async def search_dense_chunks(
    session: AsyncSession,
    query_embedding: Sequence[float],
    *,
    filters: RetrievalFilters | None = None,
    top_k: int,
    embedding_dim: int | None = None,
) -> list[RetrievalCandidate]:
    """Search pgvector chunks by cosine similarity."""
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    expected_dim = embedding_dim or get_settings().embedding_dim
    if len(query_embedding) != expected_dim:
        raise ValueError(
            f"query_embedding has dimension {len(query_embedding)}; expected {expected_dim}"
        )

    distance = GuidanceChunk.embedding.op("<=>", return_type=Float)(
        [float(value) for value in query_embedding]
    ).label("distance")
    statement = (
        select(GuidanceChunk, distance)
        .join(GuidanceRegistry, GuidanceRegistry.slug == GuidanceChunk.document_slug)
        .where(*build_postgres_filter_clauses(filters))
        .order_by(distance)
        .limit(top_k)
    )
    result = await session.execute(statement)
    return [_candidate_from_row(row, rank=rank) for rank, row in enumerate(result.all(), start=1)]


def _candidate_from_row(row: Any, *, rank: int) -> RetrievalCandidate:
    chunk_row, distance = row
    similarity = 1.0 - float(distance)
    chunk = Chunk(
        chunk_id=chunk_row.chunk_id,
        document_id=chunk_row.document_slug or chunk_row.evidence_payload.get("slug"),
        chunk_type=_chunk_type(chunk_row.chunk_type),
        parent_chunk_id=chunk_row.parent_chunk_id,
        text=chunk_row.text,
        version_hash=chunk_row.version_hash,
        source_url=chunk_row.source_url,
        section_id=chunk_row.section_id,
        section_title=chunk_row.section_title,
        page_number=chunk_row.page_number,
        char_start=chunk_row.char_start,
        char_end=chunk_row.char_end,
        token_count=chunk_row.token_count,
    )
    return RetrievalCandidate(
        chunk=chunk,
        source=RetrievalSource.DENSE,
        score=similarity,
        dense_score=similarity,
        rank=rank,
        dense_rank=rank,
        evidence_payload=dict(chunk_row.evidence_payload or {}),
    )


def _chunk_type(value: str | ChunkType) -> ChunkType:
    if isinstance(value, ChunkType):
        return value
    return ChunkType(value)
