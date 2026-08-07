"""Audit trail and alert record models for compliance and monitoring."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.documents import DocumentStatus


class AuditEventType(str, Enum):
    """Categories of auditable events."""

    QUERY = "query"
    ANSWER = "answer"
    REFUSAL = "refusal"
    CITATION_BIND = "citation_bind"
    INGESTION = "ingestion"
    EXPORT = "export"


class AuditEvent(BaseModel):
    """An immutable audit trail record for regulatory traceability."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(description="Unique audit event identifier.")
    event_type: AuditEventType = Field(description="Type of audited action.")
    user_id: str | None = Field(default=None, description="Acting user identifier.")
    session_id: str | None = Field(default=None, description="Related session id.")
    payload: dict[str, object] = Field(
        default_factory=dict,
        description="Structured event details (query, scores, document ids).",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Event timestamp (UTC)."
    )


class AlertType(str, Enum):
    """Categories of guidance-update alerts."""

    NEW = "new"
    UPDATED = "updated"
    WITHDRAWN = "withdrawn"


class AlertRecord(BaseModel):
    """A guidance-update alert produced by the monitoring pipeline."""

    model_config = ConfigDict(extra="forbid")

    alert_id: str = Field(description="Unique alert identifier.")
    alert_type: AlertType = Field(description="New, updated, or withdrawn.")
    document_id: str = Field(description="Affected document identifier.")
    title: str = Field(description="Affected guidance title.")
    previous_status: DocumentStatus | None = Field(
        default=None, description="Prior document status, if changed."
    )
    current_status: DocumentStatus = Field(description="Current document status.")
    previous_version_hash: str | None = Field(
        default=None, description="Prior version hash, if the content changed."
    )
    current_version_hash: str = Field(description="Current version hash.")
    summary: str | None = Field(default=None, description="Short human-readable change summary.")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the change was detected.",
    )
