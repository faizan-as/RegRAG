"""Tests for server-owned export contracts and artifact rendering."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.schemas.exports import ExportFormat, ExportRequest
from src.common.storage import LocalArtifactStore
from src.reports.exporter import write_export_artifact


def test_export_request_rejects_client_authored_content() -> None:
    with pytest.raises(ValidationError):
        ExportRequest.model_validate(
            {
                "export_type": "transcript",
                "session_id": "session-1",
                "answers": [{"text": "fabricated"}],
            }
        )


def test_text_export_uses_safe_namespaced_key(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    export_id, object_key, size_bytes = write_export_artifact(
        "Grounded transcript",
        ExportFormat.TEXT,
        artifact_store=store,
        export_id="export-1",
    )

    assert export_id == "export-1"
    assert object_key == "exports/export-1.txt"
    assert size_bytes > 0
    assert store.read_bytes(object_key) == b"Grounded transcript"
