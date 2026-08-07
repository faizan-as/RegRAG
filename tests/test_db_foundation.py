"""Smoke tests for Phase 2 database foundation metadata."""

from __future__ import annotations

from src.db.models import (
    AlertRecordORM,
    Base,
    ChatSessionRecord,
    ChatTurnRecord,
    GroundedSummaryRecord,
    GuidanceChunk,
    GuidanceRegistry,
    LifecycleState,
    SourceArtifact,
)


def test_guidance_registry_model_shape() -> None:
    """The registry model exposes the columns needed by Tier 1 catalog sync."""
    table = GuidanceRegistry.__table__

    assert table.name == "guidance_registry"
    assert table.primary_key.columns.keys() == ["slug"]
    assert "guidance_registry" in Base.metadata.tables
    assert GuidanceRegistry.lifecycle_state.default is not None
    assert LifecycleState.ACTIVE.value == "active"
    assert table.columns["regulated_product"].type.length == 512
    assert table.columns["docket_id"].type.length == 512

    expected_columns = {
        "slug",
        "title",
        "landing_url",
        "pdf_url",
        "status",
        "lifecycle_state",
        "center",
        "communication_type",
        "topics",
        "regulated_product",
        "docket_id",
        "docket_url",
        "issue_date",
        "comment_close_date",
        "open_comment",
        "fda_last_changed",
        "raw_payload",
        "first_seen_at",
        "last_seen_at",
        "last_synced_at",
    }
    assert expected_columns.issubset(table.columns.keys())


def test_source_artifact_model_shape() -> None:
    """Source artifacts track local storage keys and audit metadata."""
    table = SourceArtifact.__table__

    assert table.name == "source_artifacts"
    assert "source_artifacts" in Base.metadata.tables
    assert table.primary_key.columns.keys() == ["id"]
    assert table.columns["object_key"].unique
    assert table.columns["document_slug"].foreign_keys

    expected_columns = {
        "id",
        "storage_backend",
        "object_key",
        "artifact_kind",
        "content_type",
        "sha256",
        "size_bytes",
        "source_url",
        "document_slug",
        "version_hash",
        "created_at",
    }
    assert expected_columns.issubset(table.columns.keys())


def test_guidance_chunk_model_shape() -> None:
    """Guidance chunks store dense vectors and Evidence Card payload metadata."""
    table = GuidanceChunk.__table__

    assert table.name == "guidance_chunks"
    assert "guidance_chunks" in Base.metadata.tables
    assert table.primary_key.columns.keys() == ["chunk_id"]
    assert table.columns["document_slug"].foreign_keys
    assert table.columns["embedding"].type.dim == 1024

    expected_columns = {
        "chunk_id",
        "document_slug",
        "version_hash",
        "chunk_type",
        "parent_chunk_id",
        "text",
        "embedding",
        "embedding_model",
        "source_url",
        "section_id",
        "section_title",
        "page_number",
        "char_start",
        "char_end",
        "token_count",
        "evidence_payload",
        "created_at",
        "updated_at",
    }
    assert expected_columns.issubset(table.columns.keys())


def test_phase5_server_owned_record_shapes() -> None:
    """Phase 5 records enforce durable ownership and alert idempotency metadata."""
    assert ChatSessionRecord.__table__.primary_key.columns.keys() == ["id"]
    assert ChatTurnRecord.__table__.columns["session_id"].foreign_keys
    assert GroundedSummaryRecord.__table__.columns["document_slug"].foreign_keys
    assert AlertRecordORM.__table__.columns["event_fingerprint"].nullable is False
    assert any(
        constraint.name == "uq_alert_records_event_fingerprint"
        for constraint in AlertRecordORM.__table__.constraints
    )