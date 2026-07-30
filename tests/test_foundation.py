"""Smoke tests for Phase 1 foundation: settings and core models."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.api.schemas import (
    Answer,
    DocumentStatus,
    EvidenceCard,
)
from apps.api.settings import LLMProvider, Settings


def test_settings_defaults() -> None:
    """Settings load with Azure OpenAI as the default LLM provider."""
    settings = Settings()
    assert settings.llm_provider == LLMProvider.AZURE_OPENAI
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.pgvector_table == "guidance_chunks"
    assert settings.embedding_dim == 1024
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.reranker_model == "BAAI/bge-reranker-large"
    assert settings.fda_guidance_json_url.endswith("/search-for-guidance.json")
    assert settings.fda_base_url == "https://www.fda.gov"
    assert settings.parent_chunk_size == 8000
    assert settings.child_chunk_size == 1200
    assert settings.child_chunk_overlap == 150
    assert settings.embed_batch_size == 32
    assert settings.ingest_schedule_cron == "0 2 * * *"
    assert settings.object_store_backend == "local"
    assert settings.object_store_base_path.as_posix() == "data/object_store"


def _sample_evidence() -> EvidenceCard:
    return EvidenceCard(
        citation_id="[1]",
        document_id="fda-0001",
        title="Guidance for Industry",
        passage="The applicant should submit...",
        source_url="https://www.fda.gov/guidance/example",
        version_hash="a" * 64,
        document_status=DocumentStatus.FINAL,
        retrieval_score=0.82,
        rerank_score=0.91,
        confidence=0.88,
        retrieved_at=datetime.now(UTC),
    )


def test_evidence_card_required_fields() -> None:
    """An Evidence Card retains its citation and provenance fields."""
    card = _sample_evidence()
    assert card.citation_id == "[1]"
    assert card.document_status == DocumentStatus.FINAL
    assert 0.0 <= card.confidence <= 1.0


def test_answer_requires_evidence() -> None:
    """An answer carries at least one Evidence Card."""
    answer = Answer(
        text="The applicant should submit X [1].",
        evidence=[_sample_evidence()],
        confidence=0.88,
    )
    assert len(answer.evidence) >= 1
    assert not answer.refused
