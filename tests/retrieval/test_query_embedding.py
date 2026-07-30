"""Tests for query embedding helpers."""

from __future__ import annotations

import pytest

from src.retrieval.query_embedding import embed_query


def test_embed_query_uses_injected_model() -> None:
    model = _FakeEmbeddingModel(vectors=[[0.1, 0.2, 0.3]])

    vector = embed_query("What does the guidance say?", model=model)

    assert vector == [0.1, 0.2, 0.3]
    assert model.calls == [(["What does the guidance say?"], True)]


def test_embed_query_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query_text"):
        embed_query("  ", model=_FakeEmbeddingModel(vectors=[]))


def test_embed_query_rejects_wrong_vector_count() -> None:
    with pytest.raises(ValueError, match="one query"):
        embed_query("question", model=_FakeEmbeddingModel(vectors=[]))


class _FakeEmbeddingModel:
    def __init__(self, *, vectors) -> None:
        self.vectors = vectors
        self.calls = []

    def encode(self, sentences, *, normalize_embeddings=True):
        self.calls.append((list(sentences), normalize_embeddings))
        return self.vectors