"""Tests for pgvector dense indexing payloads."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.dialects import postgresql

from apps.api.schemas.chunks import Chunk, ChunkType, EmbeddedChunk
from apps.api.schemas.documents import DocumentMetadata, DocumentStatus
import src.ingestion.indexer as indexer
from src.ingestion.indexer import (
    build_guidance_chunk_rows,
    build_keyword_documents,
    delete_dense_chunks_for_document,
    delete_keyword_chunks_for_document,
    delete_keyword_chunks_for_version,
    ensure_keyword_index,
    index_keyword_chunks,
    keyword_index_mapping,
    mark_registry_indexed,
    reindex_changed_document,
    remove_withdrawn_document,
    upsert_dense_chunks,
)


class _FakeSession:
    def __init__(self, *, rowcounts: list[int] | None = None) -> None:
        self.statements = []
        self._rowcounts = rowcounts or []

    async def execute(self, statement):
        self.statements.append(statement)
        rowcount = self._rowcounts.pop(0) if self._rowcounts else 0
        return _FakeResult(rowcount=rowcount)


class _FakeResult:
    def __init__(self, *, rowcount: int) -> None:
        self.rowcount = rowcount


class _FakeIndices:
    def __init__(self, *, exists: bool) -> None:
        self._exists = exists
        self.created: list[dict] = []

    def exists(self, *, index: str) -> bool:
        return self._exists

    def create(self, *, index: str, body: dict) -> None:
        self.created.append({"index": index, "body": body})


class _FakeOpenSearchClient:
    def __init__(self, *, index_exists: bool = False) -> None:
        self.indices = _FakeIndices(exists=index_exists)
        self.delete_calls: list[dict] = []

    def delete_by_query(self, **kwargs):
        self.delete_calls.append(kwargs)
        return {"deleted": 2}


@pytest.mark.asyncio
async def test_upsert_dense_chunks_submits_pgvector_upsert() -> None:
    session = _FakeSession()
    embedded = [_embedded_chunk("example-guidance:a:1")]

    count = await upsert_dense_chunks(session, embedded)

    assert count == 1
    assert len(session.statements) == 1
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in compiled
    assert "guidance_chunks" in compiled


@pytest.mark.asyncio
async def test_upsert_dense_chunks_skips_empty_input() -> None:
    session = _FakeSession()

    count = await upsert_dense_chunks(session, [])

    assert count == 0
    assert session.statements == []


def test_build_guidance_chunk_rows_includes_evidence_payload() -> None:
    metadata = DocumentMetadata(
        document_id="example-guidance",
        title="Example Guidance",
        source_url="https://www.fda.gov/media/example/download",
        status=DocumentStatus.FINAL,
        version_hash="a" * 64,
        center="CDER",
        topics=["Clinical", "Drugs"],
        communication_type="Guidance Document",
        docket_number="FDA-2026-D-0001",
        issue_date=date(2026, 7, 21),
    )

    rows = build_guidance_chunk_rows([_embedded_chunk("example-guidance:a:1")], document_metadata=metadata)

    assert len(rows) == 1
    row = rows[0]
    assert row["chunk_id"] == "example-guidance:a:1"
    assert row["document_slug"] == "example-guidance"
    assert row["embedding"] == [0.1, 0.2, 0.3]
    assert row["embedding_model"] == "BAAI/bge-m3"
    assert row["evidence_payload"] == {
        "chunk_id": "example-guidance:a:1",
        "slug": "example-guidance",
        "doc_title": "Example Guidance",
        "version_hash": "a" * 64,
        "status": "Final",
        "center": "CDER",
        "comm_type": "Guidance Document",
        "topics": ["Clinical", "Drugs"],
        "docket_id": "FDA-2026-D-0001",
        "issue_date": "2026-07-21",
        "source_url": "https://www.fda.gov/media/example/download",
        "section_id": "i-introduction",
        "section_title": "I. INTRODUCTION",
        "page": 3,
        "char_start": 10,
        "char_end": 42,
        "parent_id": "example-guidance:a:0",
        "embedding_model": "BAAI/bge-m3",
    }


def test_ensure_keyword_index_creates_missing_index() -> None:
    client = _FakeOpenSearchClient(index_exists=False)

    created = ensure_keyword_index(client, index_name="fda_guidance")

    assert created is True
    assert client.indices.created[0]["index"] == "fda_guidance"
    assert client.indices.created[0]["body"] == keyword_index_mapping()


def test_ensure_keyword_index_skips_existing_index() -> None:
    client = _FakeOpenSearchClient(index_exists=True)

    created = ensure_keyword_index(client, index_name="fda_guidance")

    assert created is False
    assert client.indices.created == []


def test_build_keyword_documents_includes_filter_metadata_and_payload() -> None:
    metadata = _metadata()

    documents = build_keyword_documents(
        [_embedded_chunk("example-guidance:a:1")],
        document_metadata=metadata,
    )

    assert documents == [
        {
            "chunk_id": "example-guidance:a:1",
            "slug": "example-guidance",
            "doc_title": "Example Guidance",
            "version_hash": "a" * 64,
            "chunk_type": "child",
            "parent_id": "example-guidance:a:0",
            "text": "Evidence text for retrieval.",
            "status": "Final",
            "lifecycle_state": "active",
            "center": "CDER",
            "comm_type": "Guidance Document",
            "topics": ["Clinical", "Drugs"],
            "docket_id": "FDA-2026-D-0001",
            "issue_date": "2026-07-21",
            "source_url": "https://www.fda.gov/media/example/download",
            "section_id": "i-introduction",
            "section_title": "I. INTRODUCTION",
            "page": 3,
            "char_start": 10,
            "char_end": 42,
            "token_count": 4,
            "embedding_model": "BAAI/bge-m3",
            "evidence_payload": documents[0]["evidence_payload"],
        }
    ]
    assert documents[0]["evidence_payload"]["parent_id"] == "example-guidance:a:0"


def test_index_keyword_chunks_bulk_indexes_documents(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_bulk(client, actions, *, raise_on_error):
        calls.append({"client": client, "actions": list(actions), "raise_on_error": raise_on_error})
        return 1, []

    client = _FakeOpenSearchClient()
    monkeypatch.setattr(indexer, "bulk", fake_bulk)

    count = index_keyword_chunks(
        client,
        [_embedded_chunk("example-guidance:a:1")],
        index_name="fda_guidance",
        document_metadata=_metadata(),
    )

    assert count == 1
    assert calls[0]["client"] is client
    assert calls[0]["raise_on_error"] is True
    assert calls[0]["actions"][0]["_op_type"] == "index"
    assert calls[0]["actions"][0]["_index"] == "fda_guidance"
    assert calls[0]["actions"][0]["_id"] == "example-guidance:a:1"
    assert calls[0]["actions"][0]["_source"]["text"] == "Evidence text for retrieval."


def test_index_keyword_chunks_skips_empty_input(monkeypatch) -> None:
    def fail_bulk(*args, **kwargs):
        raise AssertionError("bulk should not be called")

    monkeypatch.setattr(indexer, "bulk", fail_bulk)

    assert index_keyword_chunks(_FakeOpenSearchClient(), [], index_name="fda_guidance") == 0


def test_delete_keyword_chunks_for_version_uses_slug_and_version_filters() -> None:
    client = _FakeOpenSearchClient()

    deleted = delete_keyword_chunks_for_version(
        client,
        index_name="fda_guidance",
        document_slug="example-guidance",
        version_hash="a" * 64,
    )

    assert deleted == 2
    assert client.delete_calls == [
        {
            "index": "fda_guidance",
            "body": {
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"slug": "example-guidance"}},
                            {"term": {"version_hash": "a" * 64}},
                        ]
                    }
                }
            },
            "refresh": True,
            "conflicts": "proceed",
        }
    ]


@pytest.mark.asyncio
async def test_delete_dense_chunks_for_document_deletes_by_slug() -> None:
    session = _FakeSession(rowcounts=[3])

    deleted = await delete_dense_chunks_for_document(session, document_slug="example-guidance")

    assert deleted == 3
    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "DELETE FROM guidance_chunks" in compiled
    assert "document_slug" in compiled


def test_delete_keyword_chunks_for_document_uses_slug_filter() -> None:
    client = _FakeOpenSearchClient()

    deleted = delete_keyword_chunks_for_document(
        client,
        index_name="fda_guidance",
        document_slug="example-guidance",
    )

    assert deleted == 2
    assert client.delete_calls == [
        {
            "index": "fda_guidance",
            "body": {"query": {"term": {"slug": "example-guidance"}}},
            "refresh": True,
            "conflicts": "proceed",
        }
    ]


@pytest.mark.asyncio
async def test_mark_registry_indexed_updates_last_synced_at() -> None:
    session = _FakeSession()
    synced_at = datetime(2026, 7, 22, tzinfo=UTC)

    await mark_registry_indexed(session, document_slug="example-guidance", synced_at=synced_at)

    compiled = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "UPDATE guidance_registry" in compiled
    assert "last_synced_at" in compiled
    assert "slug" in compiled


@pytest.mark.asyncio
async def test_reindex_changed_document_deletes_indexes_upserts_and_marks_synced(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    synced_at = datetime(2026, 7, 22, tzinfo=UTC)

    async def fake_delete_dense(session, *, document_slug, version_hash):
        calls.append(("delete_dense", (document_slug, version_hash)))
        return 1

    def fake_delete_keyword(client, *, index_name, document_slug, version_hash):
        calls.append(("delete_keyword", (index_name, document_slug, version_hash)))
        return 2

    def fake_ensure(client, *, index_name):
        calls.append(("ensure", index_name))
        return False

    async def fake_upsert(session, embedded_chunks, *, document_metadata):
        calls.append(("upsert", len(embedded_chunks)))
        return 3

    def fake_index(client, embedded_chunks, *, index_name, document_metadata):
        calls.append(("index", (index_name, len(embedded_chunks))))
        return 3

    async def fake_mark(session, *, document_slug, synced_at):
        calls.append(("mark", (document_slug, synced_at)))

    monkeypatch.setattr(indexer, "delete_dense_chunks_for_version", fake_delete_dense)
    monkeypatch.setattr(indexer, "delete_keyword_chunks_for_version", fake_delete_keyword)
    monkeypatch.setattr(indexer, "ensure_keyword_index", fake_ensure)
    monkeypatch.setattr(indexer, "upsert_dense_chunks", fake_upsert)
    monkeypatch.setattr(indexer, "index_keyword_chunks", fake_index)
    monkeypatch.setattr(indexer, "mark_registry_indexed", fake_mark)

    outcome = await reindex_changed_document(
        _FakeSession(),
        _FakeOpenSearchClient(),
        [_embedded_chunk("example-guidance:a:1"), _embedded_chunk("example-guidance:a:2")],
        index_name="fda_guidance",
        document_metadata=_metadata(),
        synced_at=synced_at,
    )

    assert outcome.document_slug == "example-guidance"
    assert outcome.version_hash == "a" * 64
    assert outcome.dense_deleted == 1
    assert outcome.keyword_deleted == 2
    assert outcome.dense_indexed == 3
    assert outcome.keyword_indexed == 3
    assert calls == [
        ("delete_dense", ("example-guidance", "a" * 64)),
        ("delete_keyword", ("fda_guidance", "example-guidance", "a" * 64)),
        ("ensure", "fda_guidance"),
        ("upsert", 2),
        ("index", ("fda_guidance", 2)),
        ("mark", ("example-guidance", synced_at)),
    ]


@pytest.mark.asyncio
async def test_remove_withdrawn_document_deletes_all_chunks_and_marks_synced(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    synced_at = datetime(2026, 7, 22, tzinfo=UTC)

    async def fake_delete_dense(session, *, document_slug):
        calls.append(("delete_dense", document_slug))
        return 4

    def fake_delete_keyword(client, *, index_name, document_slug):
        calls.append(("delete_keyword", (index_name, document_slug)))
        return 5

    async def fake_mark(session, *, document_slug, synced_at):
        calls.append(("mark", (document_slug, synced_at)))

    monkeypatch.setattr(indexer, "delete_dense_chunks_for_document", fake_delete_dense)
    monkeypatch.setattr(indexer, "delete_keyword_chunks_for_document", fake_delete_keyword)
    monkeypatch.setattr(indexer, "mark_registry_indexed", fake_mark)

    outcome = await remove_withdrawn_document(
        _FakeSession(),
        _FakeOpenSearchClient(),
        index_name="fda_guidance",
        document_slug="example-guidance",
        synced_at=synced_at,
    )

    assert outcome.document_slug == "example-guidance"
    assert outcome.version_hash is None
    assert outcome.dense_deleted == 4
    assert outcome.keyword_deleted == 5
    assert outcome.dense_indexed == 0
    assert outcome.keyword_indexed == 0
    assert calls == [
        ("delete_dense", "example-guidance"),
        ("delete_keyword", ("fda_guidance", "example-guidance")),
        ("mark", ("example-guidance", synced_at)),
    ]


@pytest.mark.asyncio
async def test_reindex_changed_document_requires_version_hash() -> None:
    with pytest.raises(ValueError, match="version_hash"):
        await reindex_changed_document(
            _FakeSession(),
            _FakeOpenSearchClient(),
            [],
            index_name="fda_guidance",
            document_metadata={"document_id": "example-guidance"},
        )


def test_keyword_index_mapping_defines_bm25_text_and_metadata_fields() -> None:
    properties = keyword_index_mapping()["mappings"]["properties"]

    assert properties["text"] == {"type": "text"}
    assert properties["slug"] == {"type": "keyword"}
    assert properties["topics"] == {"type": "keyword"}
    assert properties["page"] == {"type": "integer"}
    assert properties["evidence_payload"] == {"type": "object", "enabled": False}


def _metadata() -> DocumentMetadata:
    return DocumentMetadata(
        document_id="example-guidance",
        title="Example Guidance",
        source_url="https://www.fda.gov/media/example/download",
        status=DocumentStatus.FINAL,
        version_hash="a" * 64,
        center="CDER",
        topics=["Clinical", "Drugs"],
        communication_type="Guidance Document",
        docket_number="FDA-2026-D-0001",
        issue_date=date(2026, 7, 21),
    )


def _embedded_chunk(chunk_id: str) -> EmbeddedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        document_id="example-guidance",
        chunk_type=ChunkType.CHILD,
        parent_chunk_id="example-guidance:a:0",
        text="Evidence text for retrieval.",
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        section_id="i-introduction",
        section_title="I. INTRODUCTION",
        page_number=3,
        char_start=10,
        char_end=42,
        token_count=4,
    )
    return EmbeddedChunk(chunk=chunk, embedding=[0.1, 0.2, 0.3], embedding_model="BAAI/bge-m3")