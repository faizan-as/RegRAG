"""Dense pgvector indexing for embedded guidance chunks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from opensearchpy.helpers import bulk
from sqlalchemy import delete, func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.schemas.chunks import EmbeddedChunk
from apps.api.schemas.documents import DocumentMetadata
from src.db.models import GuidanceChunk, GuidanceRegistry

DocumentMetadataInput = DocumentMetadata | Mapping[str, Any] | None


@dataclass(frozen=True)
class IndexingOutcome:
    """Summary of changed/withdrawn document indexing side effects."""

    document_slug: str
    version_hash: str | None
    dense_deleted: int
    keyword_deleted: int
    dense_indexed: int
    keyword_indexed: int
    synced_at: datetime


async def reindex_changed_document(
    session: AsyncSession,
    client: Any,
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    index_name: str,
    document_metadata: DocumentMetadataInput = None,
    synced_at: datetime | None = None,
) -> IndexingOutcome:
    """Delete and reindex one changed document version across dense and BM25 stores."""
    metadata = _metadata_dict(document_metadata)
    document_slug = _document_slug(embedded_chunks, metadata)
    version_hash = _version_hash(embedded_chunks, metadata)
    timestamp = synced_at or datetime.now(UTC)

    dense_deleted = await delete_dense_chunks_for_version(
        session,
        document_slug=document_slug,
        version_hash=version_hash,
    )
    ensure_keyword_index(client, index_name=index_name)
    keyword_deleted = delete_keyword_chunks_for_version(
        client,
        index_name=index_name,
        document_slug=document_slug,
        version_hash=version_hash,
    )
    dense_indexed = await upsert_dense_chunks(
        session,
        embedded_chunks,
        document_metadata=metadata,
    )
    keyword_indexed = index_keyword_chunks(
        client,
        embedded_chunks,
        index_name=index_name,
        document_metadata=metadata,
    )
    await mark_registry_indexed(session, document_slug=document_slug, synced_at=timestamp)
    return IndexingOutcome(
        document_slug=document_slug,
        version_hash=version_hash,
        dense_deleted=dense_deleted,
        keyword_deleted=keyword_deleted,
        dense_indexed=dense_indexed,
        keyword_indexed=keyword_indexed,
        synced_at=timestamp,
    )


async def remove_withdrawn_document(
    session: AsyncSession,
    client: Any,
    *,
    index_name: str,
    document_slug: str,
    synced_at: datetime | None = None,
) -> IndexingOutcome:
    """Remove all retrieval chunks for a withdrawn document and mark registry sync time."""
    timestamp = synced_at or datetime.now(UTC)
    dense_deleted = await delete_dense_chunks_for_document(session, document_slug=document_slug)
    keyword_deleted = delete_keyword_chunks_for_document(
        client,
        index_name=index_name,
        document_slug=document_slug,
    )
    await mark_registry_indexed(session, document_slug=document_slug, synced_at=timestamp)
    return IndexingOutcome(
        document_slug=document_slug,
        version_hash=None,
        dense_deleted=dense_deleted,
        keyword_deleted=keyword_deleted,
        dense_indexed=0,
        keyword_indexed=0,
        synced_at=timestamp,
    )


async def upsert_dense_chunks(
    session: AsyncSession,
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    document_metadata: DocumentMetadataInput = None,
) -> int:
    """Upsert embedded chunks into the PostgreSQL pgvector table.

    Args:
        session: Async SQLAlchemy session.
        embedded_chunks: Embedded child chunks to persist.
        document_metadata: Optional document-level metadata for Evidence Cards.

    Returns:
        Number of embedded chunks submitted for upsert.
    """
    rows = build_guidance_chunk_rows(embedded_chunks, document_metadata=document_metadata)
    if not rows:
        return 0

    statement = insert(GuidanceChunk).values(rows)
    update_columns = {
        column.name: getattr(statement.excluded, column.name)
        for column in GuidanceChunk.__table__.columns
        if column.name not in {"chunk_id", "created_at"}
    }
    update_columns["updated_at"] = func.now()
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[GuidanceChunk.chunk_id],
            set_=update_columns,
        )
    )
    return len(rows)


async def delete_dense_chunks_for_version(
    session: AsyncSession,
    *,
    document_slug: str,
    version_hash: str,
) -> int:
    """Delete dense chunks for a document version before re-indexing."""
    result = await session.execute(
        delete(GuidanceChunk).where(
            GuidanceChunk.document_slug == document_slug,
            GuidanceChunk.version_hash == version_hash,
        )
    )
    return int(result.rowcount or 0)


async def delete_dense_chunks_for_document(
    session: AsyncSession,
    *,
    document_slug: str,
) -> int:
    """Delete all dense chunks for a withdrawn document."""
    result = await session.execute(
        delete(GuidanceChunk).where(GuidanceChunk.document_slug == document_slug)
    )
    return int(result.rowcount or 0)


async def mark_registry_indexed(
    session: AsyncSession,
    *,
    document_slug: str,
    synced_at: datetime,
) -> None:
    """Record that retrieval indexes are synchronized for a registry document."""
    await session.execute(
        update(GuidanceRegistry)
        .where(GuidanceRegistry.slug == document_slug)
        .values(last_synced_at=synced_at)
    )


def ensure_keyword_index(client: Any, *, index_name: str) -> bool:
    """Create the OpenSearch BM25 index if it does not already exist.

    Returns:
        True when the index was created, False when it already existed.
    """
    if client.indices.exists(index=index_name):
        return False
    client.indices.create(index=index_name, body=keyword_index_mapping())
    return True


def index_keyword_chunks(
    client: Any,
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    index_name: str,
    document_metadata: DocumentMetadataInput = None,
) -> int:
    """Bulk index embedded chunks into OpenSearch for BM25 keyword retrieval."""
    documents = build_keyword_documents(
        embedded_chunks,
        document_metadata=document_metadata,
    )
    if not documents:
        return 0
    actions = [
        {
            "_op_type": "index",
            "_index": index_name,
            "_id": document["chunk_id"],
            "_source": document,
        }
        for document in documents
    ]
    success_count, _ = bulk(client, actions, raise_on_error=True)
    return int(success_count)


def delete_keyword_chunks_for_version(
    client: Any,
    *,
    index_name: str,
    document_slug: str,
    version_hash: str,
) -> int:
    """Delete OpenSearch chunks for a document version before re-indexing."""
    response = client.delete_by_query(
        index=index_name,
        body={
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"slug": document_slug}},
                        {"term": {"version_hash": version_hash}},
                    ]
                }
            }
        },
        refresh=True,
        conflicts="proceed",
    )
    return int(response.get("deleted", 0))


def delete_keyword_chunks_for_document(
    client: Any,
    *,
    index_name: str,
    document_slug: str,
) -> int:
    """Delete all OpenSearch chunks for a withdrawn document."""
    response = client.delete_by_query(
        index=index_name,
        body={"query": {"term": {"slug": document_slug}}},
        refresh=True,
        conflicts="proceed",
    )
    return int(response.get("deleted", 0))


def build_keyword_documents(
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    document_metadata: DocumentMetadataInput = None,
) -> list[dict[str, Any]]:
    """Build OpenSearch BM25 documents with metadata filters and evidence payloads."""
    metadata = _metadata_dict(document_metadata)
    documents: list[dict[str, Any]] = []
    for embedded_chunk in embedded_chunks:
        chunk = embedded_chunk.chunk
        payload = _evidence_payload(embedded_chunk, metadata)
        documents.append(
            {
                "chunk_id": chunk.chunk_id,
                "slug": chunk.document_id,
                "doc_title": metadata.get("title"),
                "version_hash": chunk.version_hash or metadata.get("version_hash"),
                "chunk_type": chunk.chunk_type.value,
                "parent_id": chunk.parent_chunk_id,
                "text": chunk.text,
                "status": _metadata_value(metadata, "status"),
                "lifecycle_state": _metadata_value(metadata, "lifecycle_state"),
                "center": metadata.get("center") or metadata.get("issuing_office"),
                "comm_type": metadata.get("communication_type"),
                "topics": metadata.get("topics") or [],
                "docket_id": metadata.get("docket_number"),
                "issue_date": _json_value(metadata.get("issue_date")),
                "source_url": chunk.source_url or _json_value(metadata.get("source_url")),
                "section_id": chunk.section_id,
                "section_title": chunk.section_title,
                "page": chunk.page_number,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_count": chunk.token_count,
                "embedding_model": embedded_chunk.embedding_model,
                "evidence_payload": payload,
            }
        )
    return documents


def keyword_index_mapping() -> dict[str, Any]:
    """Return the OpenSearch mapping for BM25 chunk retrieval."""
    return {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "chunk_id": {"type": "keyword"},
                "slug": {"type": "keyword"},
                "doc_title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "version_hash": {"type": "keyword"},
                "chunk_type": {"type": "keyword"},
                "parent_id": {"type": "keyword"},
                "text": {"type": "text"},
                "status": {"type": "keyword"},
                "lifecycle_state": {"type": "keyword"},
                "center": {"type": "keyword"},
                "comm_type": {"type": "keyword"},
                "topics": {"type": "keyword"},
                "docket_id": {"type": "keyword"},
                "issue_date": {"type": "date"},
                "source_url": {"type": "keyword", "index": False},
                "section_id": {"type": "keyword"},
                "section_title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "page": {"type": "integer"},
                "char_start": {"type": "long"},
                "char_end": {"type": "long"},
                "token_count": {"type": "integer"},
                "embedding_model": {"type": "keyword"},
                "evidence_payload": {"type": "object", "enabled": False},
            },
        },
    }


def build_guidance_chunk_rows(
    embedded_chunks: Sequence[EmbeddedChunk],
    *,
    document_metadata: DocumentMetadataInput = None,
) -> list[dict[str, Any]]:
    """Build pgvector row dictionaries with Evidence Card payload metadata."""
    metadata = _metadata_dict(document_metadata)
    rows: list[dict[str, Any]] = []
    for embedded_chunk in embedded_chunks:
        chunk = embedded_chunk.chunk
        payload = _evidence_payload(embedded_chunk, metadata)
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "document_slug": chunk.document_id,
                "version_hash": chunk.version_hash or metadata.get("version_hash"),
                "chunk_type": chunk.chunk_type.value,
                "parent_chunk_id": chunk.parent_chunk_id,
                "text": chunk.text,
                "embedding": [float(value) for value in embedded_chunk.embedding],
                "embedding_model": embedded_chunk.embedding_model,
                "source_url": chunk.source_url or metadata.get("source_url"),
                "section_id": chunk.section_id,
                "section_title": chunk.section_title,
                "page_number": chunk.page_number,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_count": chunk.token_count,
                "evidence_payload": payload,
            }
        )
    return rows


def _evidence_payload(
    embedded_chunk: EmbeddedChunk,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    chunk = embedded_chunk.chunk
    return {
        "chunk_id": chunk.chunk_id,
        "slug": chunk.document_id,
        "doc_title": metadata.get("title"),
        "version_hash": chunk.version_hash or metadata.get("version_hash"),
        "status": _metadata_value(metadata, "status"),
        "center": metadata.get("center") or metadata.get("issuing_office"),
        "comm_type": metadata.get("communication_type"),
        "topics": metadata.get("topics") or [],
        "docket_id": metadata.get("docket_number"),
        "issue_date": _json_value(metadata.get("issue_date")),
        "source_url": chunk.source_url or _json_value(metadata.get("source_url")),
        "section_id": chunk.section_id,
        "section_title": chunk.section_title,
        "page": chunk.page_number,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "parent_id": chunk.parent_chunk_id,
        "embedding_model": embedded_chunk.embedding_model,
    }


def _metadata_dict(document_metadata: DocumentMetadataInput) -> dict[str, Any]:
    if document_metadata is None:
        return {}
    if isinstance(document_metadata, DocumentMetadata):
        return document_metadata.model_dump(mode="python")
    return dict(document_metadata)


def _document_slug(embedded_chunks: Sequence[EmbeddedChunk], metadata: Mapping[str, Any]) -> str:
    document_slug = metadata.get("document_id")
    if document_slug is None and embedded_chunks:
        document_slug = embedded_chunks[0].chunk.document_id
    if not isinstance(document_slug, str) or not document_slug:
        raise ValueError("document_slug could not be determined for indexing")
    return document_slug


def _version_hash(embedded_chunks: Sequence[EmbeddedChunk], metadata: Mapping[str, Any]) -> str:
    version_hash = metadata.get("version_hash")
    if version_hash is None and embedded_chunks:
        version_hash = embedded_chunks[0].chunk.version_hash
    if not isinstance(version_hash, str) or not version_hash:
        raise ValueError("version_hash could not be determined for indexing")
    return version_hash


def _metadata_value(metadata: Mapping[str, Any], key: str) -> Any:
    return _json_value(metadata[key]) if key in metadata else None


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)
