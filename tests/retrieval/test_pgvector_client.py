"""Tests for PostgreSQL + pgvector dense retrieval."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql
import pytest

from apps.api.schemas.chunks import ChunkType
from apps.api.schemas.search import RetrievalSource
from src.retrieval.pgvector_client import search_dense_chunks


async def test_search_dense_chunks_validates_embedding_dimension() -> None:
    with pytest.raises(ValueError, match="dimension"):
        await search_dense_chunks(_FakeSession([]), [0.1, 0.2], top_k=5, embedding_dim=3)


async def test_search_dense_chunks_submits_pgvector_query_and_maps_candidates() -> None:
    chunk_row = _ChunkRow()
    session = _FakeSession([(chunk_row, 0.2)])

    candidates = await search_dense_chunks(
        session,
        [0.1, 0.2, 0.3],
        top_k=5,
        embedding_dim=3,
    )

    compiled = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "guidance_chunks.embedding <=>" in compiled
    assert "guidance_registry" in compiled
    assert candidates[0].chunk.chunk_id == "example-guidance:a:1"
    assert candidates[0].chunk.chunk_type == ChunkType.CHILD
    assert candidates[0].chunk.page_number == 3
    assert candidates[0].source == RetrievalSource.DENSE
    assert candidates[0].score == pytest.approx(0.8)
    assert candidates[0].dense_score == pytest.approx(0.8)
    assert candidates[0].dense_rank == 1
    assert candidates[0].evidence_payload["doc_title"] == "Example Guidance"


async def test_search_dense_chunks_rejects_invalid_top_k() -> None:
    with pytest.raises(ValueError, match="top_k"):
        await search_dense_chunks(_FakeSession([]), [0.1], top_k=0, embedding_dim=1)


class _FakeSession:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _FakeResult(self.rows)


class _FakeResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class _ChunkRow:
    chunk_id = "example-guidance:a:1"
    document_slug = "example-guidance"
    version_hash = "a" * 64
    chunk_type = "child"
    parent_chunk_id = "example-guidance:a:0"
    text = "Evidence text for retrieval."
    source_url = "https://www.fda.gov/media/example/download"
    section_id = "i-introduction"
    section_title = "I. INTRODUCTION"
    page_number = 3
    char_start = 10
    char_end = 42
    token_count = 4
    evidence_payload = {
        "slug": "example-guidance",
        "doc_title": "Example Guidance",
        "page": 3,
    }