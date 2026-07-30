"""Embedding generation for ingestion chunks."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from apps.api.schemas.chunks import Chunk, ChunkType, EmbeddedChunk


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"


@runtime_checkable
class EmbeddingModel(Protocol):
    """Minimal sentence-transformers compatible embedding model protocol."""

    def encode(
        self,
        sentences: Sequence[str],
        *,
        normalize_embeddings: bool = True,
    ) -> object:
        """Encode text into dense vectors."""


@dataclass(frozen=True)
class EmbeddingProgress:
    """Progress snapshot emitted after each embedding batch."""

    batch_index: int
    batch_count: int
    batch_size: int
    embedded_count: int
    total_count: int


ProgressCallback = Callable[[EmbeddingProgress], None]


def embed_chunks(
    chunks: Iterable[Chunk],
    *,
    model: EmbeddingModel | None = None,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
    progress_callback: ProgressCallback | None = None,
) -> list[EmbeddedChunk]:
    """Embed child chunks with BGE-M3-compatible batching.

    Args:
        chunks: Parent-child ingestion chunks. Only child chunks are embedded.
        model: Optional injected model for tests or preloaded production use.
        model_name: Sentence-transformers model name to load when ``model`` is not provided.
        batch_size: Number of child chunks to embed per model call.
        progress_callback: Optional callback invoked after every completed batch.

    Returns:
        Embedded child chunks in input order.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")

    child_chunks = [chunk for chunk in chunks if chunk.chunk_type == ChunkType.CHILD]
    if not child_chunks:
        return []

    embedding_model = model or load_embedding_model(model_name)
    embedded_chunks: list[EmbeddedChunk] = []
    batch_count = _batch_count(len(child_chunks), batch_size)

    for batch_index, batch in enumerate(_batched(child_chunks, batch_size), start=1):
        vectors = _encode_batch(embedding_model, [chunk.text for chunk in batch])
        if len(vectors) != len(batch):
            raise ValueError(
                f"Embedding model returned {len(vectors)} vectors for {len(batch)} chunks"
            )
        embedded_chunks.extend(
            EmbeddedChunk(chunk=chunk, embedding=vector, embedding_model=model_name)
            for chunk, vector in zip(batch, vectors, strict=True)
        )
        if progress_callback is not None:
            progress_callback(
                EmbeddingProgress(
                    batch_index=batch_index,
                    batch_count=batch_count,
                    batch_size=len(batch),
                    embedded_count=len(embedded_chunks),
                    total_count=len(child_chunks),
                )
            )

    return embedded_chunks


def load_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL) -> EmbeddingModel:
    """Load a sentence-transformers embedding model lazily."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required for BGE-M3 embedding generation."
        ) from exc
    return SentenceTransformer(model_name)


def _encode_batch(model: EmbeddingModel, texts: Sequence[str]) -> list[list[float]]:
    raw_vectors = model.encode(texts, normalize_embeddings=True)
    return [_as_float_vector(vector) for vector in raw_vectors]  # type: ignore[union-attr]


def _as_float_vector(vector: object) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()  # type: ignore[assignment, attr-defined]
    return [float(value) for value in vector]  # type: ignore[union-attr]


def _batched(chunks: Sequence[Chunk], batch_size: int) -> Iterable[list[Chunk]]:
    for start in range(0, len(chunks), batch_size):
        yield list(chunks[start : start + batch_size])


def _batch_count(total_count: int, batch_size: int) -> int:
    return (total_count + batch_size - 1) // batch_size