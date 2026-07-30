"""Tests for OpenSearch BM25 retrieval."""

from __future__ import annotations

import pytest

from apps.api.schemas.chunks import ChunkType
from apps.api.schemas.search import RetrievalSource
from src.retrieval.filters import RetrievalFilters
from src.retrieval.opensearch_client import keyword_search_body, search_keyword_chunks


def test_keyword_search_body_builds_multi_match_and_filters() -> None:
    body = keyword_search_body(
        "labeling requirements",
        filters=RetrievalFilters(center="CDER"),
        top_k=10,
    )

    assert body["size"] == 10
    assert body["query"]["bool"]["must"][0]["multi_match"]["query"] == "labeling requirements"
    assert "text^3" in body["query"]["bool"]["must"][0]["multi_match"]["fields"]
    assert {"term": {"center": "CDER"}} in body["query"]["bool"]["filter"]


def test_search_keyword_chunks_maps_hits_to_candidates() -> None:
    client = _FakeOpenSearchClient(
        hits=[
            {
                "_score": 7.5,
                "_source": {
                    "chunk_id": "example-guidance:a:1",
                    "slug": "example-guidance",
                    "version_hash": "a" * 64,
                    "chunk_type": "child",
                    "parent_id": "example-guidance:a:0",
                    "text": "Evidence text for retrieval.",
                    "source_url": "https://www.fda.gov/media/example/download",
                    "section_id": "i-introduction",
                    "section_title": "I. INTRODUCTION",
                    "page": 3,
                    "char_start": 10,
                    "char_end": 42,
                    "token_count": 4,
                    "evidence_payload": {"doc_title": "Example Guidance", "page": 3},
                },
            }
        ]
    )

    candidates = search_keyword_chunks(
        client,
        "labeling requirements",
        filters=RetrievalFilters(center="CDER"),
        top_k=5,
        index_name="fda_guidance",
    )

    assert client.calls[0]["index"] == "fda_guidance"
    assert candidates[0].chunk.chunk_id == "example-guidance:a:1"
    assert candidates[0].chunk.chunk_type == ChunkType.CHILD
    assert candidates[0].chunk.page_number == 3
    assert candidates[0].source == RetrievalSource.KEYWORD
    assert candidates[0].score == 7.5
    assert candidates[0].keyword_score == 7.5
    assert candidates[0].keyword_rank == 1
    assert candidates[0].evidence_payload["doc_title"] == "Example Guidance"


def test_search_keyword_chunks_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="query_text"):
        search_keyword_chunks(_FakeOpenSearchClient(hits=[]), " ", top_k=5, index_name="idx")
    with pytest.raises(ValueError, match="top_k"):
        search_keyword_chunks(_FakeOpenSearchClient(hits=[]), "query", top_k=0, index_name="idx")


class _FakeOpenSearchClient:
    def __init__(self, *, hits) -> None:
        self.hits = hits
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return {"hits": {"hits": self.hits}}