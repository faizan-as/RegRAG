"""Smoke tests for remaining Phase 2 foundation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from apps.api.schemas import DocumentMetadata, DocumentStatus, DocumentVersion
from src.common.clients import PgvectorConfig, get_pgvector_config
from src.common.storage import LocalArtifactStore
from src.db.models import LifecycleState


def test_pgvector_config_uses_settings_defaults() -> None:
    """Shared pgvector config exposes the configured table and dimension."""
    config = get_pgvector_config()

    assert isinstance(config, PgvectorConfig)
    assert config.table_name == "guidance_chunks"
    assert config.embedding_dim == 1024


def test_document_metadata_accepts_catalog_fields() -> None:
    """Document metadata includes catalog fields needed by Tier 1 and filters."""
    metadata = DocumentMetadata(
        document_id="example-guidance",
        title="Example Guidance",
        source_url="https://www.fda.gov/regulatory-information/example-guidance",
        status=DocumentStatus.FINAL,
        version_hash="a" * 64,
        center="CDER",
        topic="Clinical",
        topics=["Clinical", "Drugs"],
        communication_type="Guidance Document",
        regulated_product="Drugs",
        fda_last_changed=datetime.now(UTC),
        lifecycle_state=LifecycleState.ACTIVE,
    )

    assert metadata.document_id == "example-guidance"
    assert metadata.center == "CDER"
    assert metadata.topics == ["Clinical", "Drugs"]
    assert metadata.lifecycle_state == LifecycleState.ACTIVE


def test_document_version_snapshot_fields() -> None:
    """Document versions carry preserved source and hash metadata."""
    version = DocumentVersion(
        document_id="example-guidance",
        version_hash="b" * 64,
        source_url="https://www.fda.gov/media/example.pdf",
        raw_object_key="raw/example-guidance/hash.pdf",
        status=DocumentStatus.DRAFT,
    )

    assert version.raw_object_key.endswith("hash.pdf")
    assert version.lifecycle_state == LifecycleState.ACTIVE


def test_local_artifact_store_writes_and_hashes_bytes(tmp_path: Path) -> None:
    """Local artifact writes are path-safe and return deterministic metadata."""
    store = LocalArtifactStore(tmp_path)
    payload = b'{"data": []}'

    result = store.put_bytes(
        "catalog/search-for-guidance/sample.json",
        payload,
        content_type="application/json",
    )

    assert result.object_key == "catalog/search-for-guidance/sample.json"
    assert result.path.exists()
    assert result.size_bytes == len(payload)
    assert store.read_bytes(result.object_key) == payload


def test_local_artifact_store_rejects_path_escape(tmp_path: Path) -> None:
    """Artifact keys cannot escape the configured base directory."""
    store = LocalArtifactStore(tmp_path)

    try:
        store.put_bytes("../escape.json", b"{}")
    except ValueError as exc:
        assert "safe relative path" in str(exc)
    else:
        raise AssertionError("Expected unsafe artifact key to be rejected")