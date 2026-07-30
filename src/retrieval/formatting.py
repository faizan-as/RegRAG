"""Formatting helpers for SearchResult and Evidence Card outputs."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from apps.api.schemas.documents import DocumentStatus
from apps.api.schemas.evidence import EvidenceCard
from apps.api.schemas.search import SearchResult
from src.retrieval.models import RetrievalCandidate


class EvidenceFormattingError(ValueError):
    """Raised when a retrieval candidate cannot be converted to an Evidence Card."""


def candidates_to_search_results(candidates: list[RetrievalCandidate]) -> list[SearchResult]:
    """Convert internal candidates to public search results."""
    return [
        SearchResult(
            chunk=candidate.chunk,
            source=candidate.source,
            score=candidate.score,
            dense_score=candidate.dense_score,
            keyword_score=candidate.keyword_score,
            rrf_score=candidate.rrf_score,
            rerank_score=candidate.rerank_score,
            rank=candidate.rank,
        )
        for candidate in candidates
    ]


def candidates_to_evidence_cards(
    candidates: list[RetrievalCandidate],
    *,
    retrieved_at: datetime | None = None,
) -> list[EvidenceCard]:
    """Convert reranked retrieval candidates to citation-ready Evidence Cards."""
    timestamp = retrieved_at or datetime.now(UTC)
    return [
        candidate_to_evidence_card(candidate, citation_id=f"[{index}]", retrieved_at=timestamp)
        for index, candidate in enumerate(candidates, start=1)
    ]


def candidate_to_evidence_card(
    candidate: RetrievalCandidate,
    *,
    citation_id: str,
    retrieved_at: datetime | None = None,
) -> EvidenceCard:
    """Convert one candidate to an Evidence Card, failing closed on missing fields."""
    payload = candidate.evidence_payload
    document_id = _required("document_id", payload.get("slug") or candidate.chunk.document_id)
    title = _required("title", payload.get("doc_title"))
    source_url = _required("source_url", payload.get("source_url") or candidate.chunk.source_url)
    version_hash = _required("version_hash", payload.get("version_hash") or candidate.chunk.version_hash)
    status = _required("document_status", payload.get("status"))
    retrieval_score = _retrieval_score(candidate)
    rerank_score = _required_score("rerank_score", candidate.rerank_score)
    confidence = 0.0 if candidate.reranker_failed else confidence_from_rerank_score(rerank_score)

    return EvidenceCard(
        citation_id=citation_id,
        document_id=document_id,
        title=title,
        section_id=payload.get("section_id") or candidate.chunk.section_id,
        section_title=payload.get("section_title") or candidate.chunk.section_title,
        page_number=_page_number(payload, candidate),
        passage=_required("passage", candidate.chunk.text),
        source_url=source_url,
        version_hash=version_hash,
        document_status=DocumentStatus(status),
        retrieval_score=retrieval_score,
        rerank_score=rerank_score,
        confidence=confidence,
        retrieved_at=retrieved_at or datetime.now(UTC),
    )


def confidence_from_rerank_score(rerank_score: float) -> float:
    """Map a rerank score into the MVP confidence range [0, 1]."""
    return 1.0 / (1.0 + math.exp(-rerank_score))


def _retrieval_score(candidate: RetrievalCandidate) -> float:
    score = candidate.rrf_score if candidate.rrf_score is not None else candidate.score
    return _required_score("retrieval_score", score)


def _page_number(payload: dict[str, Any], candidate: RetrievalCandidate) -> int | None:
    page = payload.get("page") or payload.get("page_number") or candidate.chunk.page_number
    return int(page) if page is not None else None


def _required(field_name: str, value: Any) -> Any:
    if value is None or value == "":
        raise EvidenceFormattingError(f"Missing required Evidence Card field: {field_name}")
    return value


def _required_score(field_name: str, value: float | None) -> float:
    if value is None:
        raise EvidenceFormattingError(f"Missing required Evidence Card field: {field_name}")
    return float(value)