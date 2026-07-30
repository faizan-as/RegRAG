"""Query embedding helpers for dense retrieval."""

from __future__ import annotations

from src.ingestion.embedder import DEFAULT_EMBEDDING_MODEL, EmbeddingModel, load_embedding_model


def embed_query(
    query_text: str,
    *,
    model: EmbeddingModel | None = None,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> list[float]:
    """Embed a single query string with a BGE-M3-compatible model."""
    if not query_text.strip():
        raise ValueError("query_text must not be empty")

    embedding_model = model or load_embedding_model(model_name)
    raw_vectors = embedding_model.encode([query_text], normalize_embeddings=True)
    vectors = [_as_float_vector(vector) for vector in raw_vectors]  # type: ignore[union-attr]
    if len(vectors) != 1:
        raise ValueError(f"Embedding model returned {len(vectors)} vectors for one query")
    return vectors[0]


def _as_float_vector(vector: object) -> list[float]:
    if hasattr(vector, "tolist"):
        vector = vector.tolist()  # type: ignore[assignment, attr-defined]
    return [float(value) for value in vector]  # type: ignore[union-attr]