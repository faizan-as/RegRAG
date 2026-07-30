"""Tests for chunk embedding generation."""

from __future__ import annotations

import builtins

import pytest

from apps.api.schemas.chunks import Chunk, ChunkType
from src.ingestion.embedder import EmbeddingProgress, embed_chunks, load_embedding_model


class _FakeEmbeddingModel:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def encode(self, sentences, *, normalize_embeddings=True):
        assert normalize_embeddings is True
        self.calls.append(list(sentences))
        return [[float(len(sentence)), float(index)] for index, sentence in enumerate(sentences)]


def test_embed_chunks_embeds_child_chunks_in_batches_and_reports_progress() -> None:
    model = _FakeEmbeddingModel()
    progress: list[EmbeddingProgress] = []
    chunks = [
        _chunk("parent", ChunkType.PARENT, "Parent text"),
        _chunk("child-1", ChunkType.CHILD, "Alpha"),
        _chunk("child-2", ChunkType.CHILD, "Beta text"),
        _chunk("child-3", ChunkType.CHILD, "Gamma body"),
    ]

    embedded = embed_chunks(
        chunks,
        model=model,
        model_name="BAAI/bge-m3",
        batch_size=2,
        progress_callback=progress.append,
    )

    assert [item.chunk.chunk_id for item in embedded] == ["child-1", "child-2", "child-3"]
    assert [item.embedding for item in embedded] == [[5.0, 0.0], [9.0, 1.0], [10.0, 0.0]]
    assert all(item.embedding_model == "BAAI/bge-m3" for item in embedded)
    assert model.calls == [["Alpha", "Beta text"], ["Gamma body"]]
    assert progress == [
        EmbeddingProgress(
            batch_index=1,
            batch_count=2,
            batch_size=2,
            embedded_count=2,
            total_count=3,
        ),
        EmbeddingProgress(
            batch_index=2,
            batch_count=2,
            batch_size=1,
            embedded_count=3,
            total_count=3,
        ),
    ]


def test_embed_chunks_returns_empty_for_no_child_chunks() -> None:
    model = _FakeEmbeddingModel()

    assert embed_chunks([_chunk("parent", ChunkType.PARENT, "Parent")], model=model) == []
    assert model.calls == []


def test_embed_chunks_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        embed_chunks([_chunk("child", ChunkType.CHILD, "Text")], model=_FakeEmbeddingModel(), batch_size=0)


def test_embed_chunks_rejects_vector_count_mismatch() -> None:
    class BadModel:
        def encode(self, sentences, *, normalize_embeddings=True):
            return [[1.0]]

    with pytest.raises(ValueError, match="returned 1 vectors for 2 chunks"):
        embed_chunks(
            [_chunk("child-1", ChunkType.CHILD, "One"), _chunk("child-2", ChunkType.CHILD, "Two")],
            model=BadModel(),
        )


def test_load_embedding_model_reports_missing_dependency(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentence_transformers":
            raise ImportError("missing sentence-transformers")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="sentence-transformers is required"):
        load_embedding_model("BAAI/bge-m3")


def _chunk(chunk_id: str, chunk_type: ChunkType, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="example-guidance",
        chunk_type=chunk_type,
        parent_chunk_id="parent" if chunk_type == ChunkType.CHILD else None,
        text=text,
        version_hash="a" * 64,
        source_url="https://www.fda.gov/media/example/download",
        section_id="i-introduction",
        section_title="I. INTRODUCTION",
        page_number=1,
        char_start=0,
        char_end=len(text),
        token_count=len(text.split()),
    )