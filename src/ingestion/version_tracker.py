"""Version snapshot and transition helpers for FDA guidance ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from apps.api.schemas import DocumentStatus, DocumentVersion
from src.db.models import GuidanceRegistry, LifecycleState, SourceArtifact
from src.ingestion.content_acquisition import AcquiredGuidanceContent


class VersionEventType(str, Enum):
    """Version and lifecycle events emitted during Tier 2 ingestion."""

    NEW_VERSION = "new_version"
    STATUS_CHANGED = "status_changed"
    LIFECYCLE_CHANGED = "lifecycle_changed"
    SUPERSEDES_VERSION = "supersedes_version"


@dataclass(frozen=True)
class VersionEvent:
    """A detected status, lifecycle, or version transition."""

    event_type: VersionEventType
    document_slug: str
    previous_value: str | None = None
    current_value: str | None = None


@dataclass(frozen=True)
class VersionTrackingResult:
    """Version snapshot and transition events for an acquired source artifact."""

    version: DocumentVersion
    events: list[VersionEvent]
    unchanged: bool


def track_document_version(
    guidance: GuidanceRegistry,
    acquired: AcquiredGuidanceContent,
    *,
    previous_artifact: SourceArtifact | None = None,
    previous_status: str | None = None,
    previous_lifecycle_state: LifecycleState | None = None,
    superseded_artifact: SourceArtifact | None = None,
    created_at: datetime | None = None,
) -> VersionTrackingResult:
    """Create a document-version snapshot and detect Tier 2 transition events."""
    supersedes_version_hash = _supersedes_version_hash(
        acquired,
        previous_artifact=previous_artifact,
        superseded_artifact=superseded_artifact,
    )
    version = DocumentVersion(
        document_id=guidance.slug,
        version_hash=acquired.version_hash,
        source_url=acquired.source_url,
        raw_object_key=acquired.raw_object_key,
        status=_document_status(guidance.status),
        lifecycle_state=guidance.lifecycle_state,
        fda_last_changed=guidance.fda_last_changed,
        supersedes_version_hash=supersedes_version_hash,
        created_at=created_at or datetime.now(UTC),
    )
    events = _version_events(
        guidance,
        acquired,
        previous_artifact=previous_artifact,
        previous_status=previous_status,
        previous_lifecycle_state=previous_lifecycle_state,
        supersedes_version_hash=supersedes_version_hash,
    )
    return VersionTrackingResult(
        version=version,
        events=events,
        unchanged=previous_artifact is not None
        and previous_artifact.version_hash == acquired.version_hash,
    )


def _version_events(
    guidance: GuidanceRegistry,
    acquired: AcquiredGuidanceContent,
    *,
    previous_artifact: SourceArtifact | None,
    previous_status: str | None,
    previous_lifecycle_state: LifecycleState | None,
    supersedes_version_hash: str | None,
) -> list[VersionEvent]:
    events: list[VersionEvent] = []
    if previous_artifact is None or previous_artifact.version_hash != acquired.version_hash:
        events.append(
            VersionEvent(
                event_type=VersionEventType.NEW_VERSION,
                document_slug=guidance.slug,
                previous_value=previous_artifact.version_hash if previous_artifact else None,
                current_value=acquired.version_hash,
            )
        )

    if previous_status is not None and previous_status != guidance.status:
        events.append(
            VersionEvent(
                event_type=VersionEventType.STATUS_CHANGED,
                document_slug=guidance.slug,
                previous_value=previous_status,
                current_value=guidance.status,
            )
        )

    if previous_lifecycle_state is not None and previous_lifecycle_state != guidance.lifecycle_state:
        events.append(
            VersionEvent(
                event_type=VersionEventType.LIFECYCLE_CHANGED,
                document_slug=guidance.slug,
                previous_value=previous_lifecycle_state.value,
                current_value=guidance.lifecycle_state.value,
            )
        )

    if supersedes_version_hash is not None:
        events.append(
            VersionEvent(
                event_type=VersionEventType.SUPERSEDES_VERSION,
                document_slug=guidance.slug,
                previous_value=supersedes_version_hash,
                current_value=acquired.version_hash,
            )
        )

    return events


def _supersedes_version_hash(
    acquired: AcquiredGuidanceContent,
    *,
    previous_artifact: SourceArtifact | None,
    superseded_artifact: SourceArtifact | None,
) -> str | None:
    if previous_artifact is not None and previous_artifact.version_hash != acquired.version_hash:
        return previous_artifact.version_hash
    if superseded_artifact is not None and superseded_artifact.version_hash != acquired.version_hash:
        return superseded_artifact.version_hash
    return None


def _document_status(status: str | None) -> DocumentStatus:
    if status == DocumentStatus.DRAFT.value:
        return DocumentStatus.DRAFT
    if status == DocumentStatus.WITHDRAWN.value:
        return DocumentStatus.WITHDRAWN
    return DocumentStatus.FINAL