"""Tests for Tier 2 document version tracking."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.api.schemas import DocumentStatus
from src.db.models import GuidanceRegistry, LifecycleState, SourceArtifact
from src.ingestion.content_acquisition import AcquiredGuidanceContent
from src.ingestion.version_tracker import VersionEventType, track_document_version


def test_track_document_version_creates_snapshot_for_new_version() -> None:
    """A newly acquired source creates a DocumentVersion and NEW_VERSION event."""
    guidance = _guidance(status="Draft")
    acquired = _acquired(version_hash="b" * 64)

    result = track_document_version(
        guidance,
        acquired,
        created_at=datetime(2026, 7, 20, tzinfo=UTC),
    )

    assert result.version.document_id == guidance.slug
    assert result.version.version_hash == acquired.version_hash
    assert result.version.raw_object_key == acquired.raw_object_key
    assert result.version.status == DocumentStatus.DRAFT
    assert result.version.lifecycle_state == LifecycleState.ACTIVE
    assert result.unchanged is False
    assert [event.event_type for event in result.events] == [VersionEventType.NEW_VERSION]


def test_track_document_version_detects_draft_to_final_transition() -> None:
    """Status changes such as Draft to Final are recorded as transition events."""
    guidance = _guidance(status="Final")
    previous = _artifact(version_hash="a" * 64)
    acquired = _acquired(version_hash="b" * 64)

    result = track_document_version(
        guidance,
        acquired,
        previous_artifact=previous,
        previous_status="Draft",
    )

    event_types = [event.event_type for event in result.events]
    assert VersionEventType.NEW_VERSION in event_types
    assert VersionEventType.STATUS_CHANGED in event_types
    assert VersionEventType.SUPERSEDES_VERSION in event_types
    assert result.version.supersedes_version_hash == previous.version_hash


def test_track_document_version_detects_active_to_withdrawn_transition() -> None:
    """Lifecycle transitions are recorded for withdrawn registry rows."""
    guidance = _guidance(status="Final", lifecycle_state=LifecycleState.WITHDRAWN)
    acquired = _acquired(version_hash="c" * 64)

    result = track_document_version(
        guidance,
        acquired,
        previous_lifecycle_state=LifecycleState.ACTIVE,
    )

    lifecycle_events = [
        event for event in result.events if event.event_type == VersionEventType.LIFECYCLE_CHANGED
    ]
    assert len(lifecycle_events) == 1
    assert lifecycle_events[0].previous_value == "active"
    assert lifecycle_events[0].current_value == "withdrawn"


def test_track_document_version_marks_unchanged_existing_artifact() -> None:
    """Existing source artifacts with the same hash do not emit new version events."""
    guidance = _guidance(status="Final")
    previous = _artifact(version_hash="d" * 64)
    acquired = _acquired(version_hash="d" * 64)

    result = track_document_version(guidance, acquired, previous_artifact=previous)

    assert result.unchanged is True
    assert result.version.supersedes_version_hash is None
    assert result.events == []


def test_track_document_version_can_supersede_same_docket_artifact() -> None:
    """Superseded artifacts from related docket rows are carried into version metadata."""
    guidance = _guidance(status="Final")
    superseded = _artifact(document_slug="older-related-guidance", version_hash="e" * 64)
    acquired = _acquired(version_hash="f" * 64)

    result = track_document_version(
        guidance,
        acquired,
        superseded_artifact=superseded,
    )

    assert result.version.supersedes_version_hash == superseded.version_hash
    assert result.events[-1].event_type == VersionEventType.SUPERSEDES_VERSION


def _guidance(
    *,
    status: str,
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE,
) -> GuidanceRegistry:
    return GuidanceRegistry(
        slug="example-guidance",
        title="Example Guidance",
        landing_url="https://www.fda.gov/regulatory-information/example-guidance",
        pdf_url="https://www.fda.gov/media/example/download",
        status=status,
        lifecycle_state=lifecycle_state,
        docket_id="FDA-2026-D-0001",
        fda_last_changed=datetime(2026, 7, 20, tzinfo=UTC),
        raw_payload={},
        topics=[],
    )


def _acquired(*, version_hash: str) -> AcquiredGuidanceContent:
    artifact = _artifact(version_hash=version_hash)
    return AcquiredGuidanceContent(
        document_slug="example-guidance",
        source_url="https://www.fda.gov/media/example/download",
        artifact=artifact,
        raw_object_key=artifact.object_key,
        version_hash=version_hash,
        content_type="application/pdf",
        size_bytes=10,
    )


def _artifact(
    *,
    version_hash: str,
    document_slug: str = "example-guidance",
) -> SourceArtifact:
    return SourceArtifact(
        storage_backend="local",
        object_key=f"raw/{document_slug}/{version_hash}.pdf",
        artifact_kind="raw_pdf",
        content_type="application/pdf",
        sha256=version_hash,
        size_bytes=10,
        source_url="https://www.fda.gov/media/example/download",
        document_slug=document_slug,
        version_hash=version_hash,
    )