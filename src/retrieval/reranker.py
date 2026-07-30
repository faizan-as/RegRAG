"""BGE-Reranker-Large cross-encoder wrapper."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from apps.api.schemas.search import RetrievalSource
from apps.api.settings import get_settings
from src.retrieval.models import RetrievalCandidate


@runtime_checkable
class RerankerModel(Protocol):
    """Minimal sentence-transformers CrossEncoder-compatible protocol."""

    def predict(self, pairs: Sequence[tuple[str, str]]) -> object:
        """Score query/candidate text pairs."""


def rerank_results(
    query_text: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    model: RerankerModel | None = None,
    model_name: str | None = None,
    top_k: int,
    batch_size: int = 16,
) -> list[RetrievalCandidate]:
    """Rerank retrieval candidates with a cross-encoder model."""
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    if not candidates:
        return []

    reranker = model or load_reranker_model(model_name or get_settings().reranker_model)
    scored: list[RetrievalCandidate] = []
    for batch in _batched(list(candidates), batch_size):
        pairs = [(query_text, candidate.chunk.text) for candidate in batch]
        scores = _as_float_scores(reranker.predict(pairs))
        if len(scores) != len(batch):
            raise ValueError(f"Reranker returned {len(scores)} scores for {len(batch)} candidates")
        scored.extend(
            candidate.with_updates(
                source=RetrievalSource.RERANKED,
                score=score,
                rerank_score=score,
                reranker_failed=False,
            )
            for candidate, score in zip(batch, scores, strict=True)
        )

    scored.sort(key=lambda candidate: (-candidate.rerank_score, candidate.chunk_id))
    return [candidate.with_updates(rank=rank) for rank, candidate in enumerate(scored[:top_k], start=1)]


def load_reranker_model(model_name: str) -> RerankerModel:
    """Load a sentence-transformers cross-encoder lazily."""
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:
        raise RuntimeError("sentence-transformers is required for BGE reranking.") from exc
    return CrossEncoder(model_name)


def _batched(candidates: Sequence[RetrievalCandidate], batch_size: int):
    for start in range(0, len(candidates), batch_size):
        yield list(candidates[start : start + batch_size])


def _as_float_scores(scores: object) -> list[float]:
    if hasattr(scores, "tolist"):
        scores = scores.tolist()  # type: ignore[assignment, attr-defined]
    return [float(score) for score in scores]  # type: ignore[union-attr]