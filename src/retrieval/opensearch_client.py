"""OpenSearch BM25 retrieval client."""

from __future__ import annotations

from typing import Any

from apps.api.schemas.chunks import Chunk, ChunkType
from apps.api.schemas.search import RetrievalSource
from src.retrieval.filters import RetrievalFilters, build_opensearch_filter_clauses
from src.retrieval.models import RetrievalCandidate


def search_keyword_chunks(
    client: Any,
    query_text: str,
    *,
    filters: RetrievalFilters | None = None,
    top_k: int,
    index_name: str,
) -> list[RetrievalCandidate]:
    """Search OpenSearch keyword chunks with BM25 scoring."""
    if not query_text.strip():
        raise ValueError("query_text must not be empty")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    body = keyword_search_body(query_text, filters=filters, top_k=top_k)
    response = client.search(index=index_name, body=body)
    hits = response.get("hits", {}).get("hits", [])
    return [_candidate_from_hit(hit, rank=rank) for rank, hit in enumerate(hits, start=1)]


def keyword_search_body(
    query_text: str,
    *,
    filters: RetrievalFilters | None = None,
    top_k: int,
) -> dict[str, Any]:
    """Build the OpenSearch request body for keyword retrieval."""
    return {
        "size": top_k,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": ["text^3", "doc_title^2", "section_title"],
                            "type": "best_fields",
                        }
                    }
                ],
                "filter": build_opensearch_filter_clauses(filters),
            }
        },
    }


def _candidate_from_hit(hit: dict[str, Any], *, rank: int) -> RetrievalCandidate:
    source = hit.get("_source", {})
    payload = dict(source.get("evidence_payload") or {})
    chunk = Chunk(
        chunk_id=source["chunk_id"],
        document_id=source.get("slug") or payload.get("slug"),
        chunk_type=_chunk_type(source.get("chunk_type", ChunkType.CHILD.value)),
        parent_chunk_id=source.get("parent_id") or payload.get("parent_id"),
        text=source["text"],
        version_hash=source.get("version_hash") or payload.get("version_hash"),
        source_url=source.get("source_url") or payload.get("source_url"),
        section_id=source.get("section_id") or payload.get("section_id"),
        section_title=source.get("section_title") or payload.get("section_title"),
        page_number=source.get("page") or payload.get("page") or payload.get("page_number"),
        char_start=source.get("char_start") or payload.get("char_start"),
        char_end=source.get("char_end") or payload.get("char_end"),
        token_count=source.get("token_count"),
    )
    score = float(hit.get("_score", 0.0))
    return RetrievalCandidate(
        chunk=chunk,
        source=RetrievalSource.KEYWORD,
        score=score,
        keyword_score=score,
        rank=rank,
        keyword_rank=rank,
        evidence_payload=payload,
    )


def _chunk_type(value: str | ChunkType) -> ChunkType:
    if isinstance(value, ChunkType):
        return value
    return ChunkType(value)