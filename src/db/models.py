"""SQLAlchemy models for FDA guidance ingestion metadata."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Enum as SAEnum


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


class LifecycleState(str, Enum):
    """Registry lifecycle states derived from FDA catalog diffs."""

    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class GuidanceRegistry(Base):
    """Catalog-level FDA guidance record keyed by FDA landing-page slug."""

    __tablename__ = "guidance_registry"
    __table_args__ = (
        Index("ix_guidance_registry_status", "status"),
        Index("ix_guidance_registry_center", "center"),
        Index("ix_guidance_registry_docket_id", "docket_id"),
        Index("ix_guidance_registry_fda_last_changed", "fda_last_changed"),
        Index("ix_guidance_registry_lifecycle_state", "lifecycle_state"),
    )

    slug: Mapped[str] = mapped_column(String(512), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    landing_url: Mapped[str | None] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str | None] = mapped_column(String(50))
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        SAEnum(
            LifecycleState,
            name="lifecycle_state",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=LifecycleState.ACTIVE,
        server_default=LifecycleState.ACTIVE.value,
    )

    center: Mapped[str | None] = mapped_column(String(100))
    communication_type: Mapped[str | None] = mapped_column(String(255))
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    regulated_product: Mapped[str | None] = mapped_column(String(512))

    docket_id: Mapped[str | None] = mapped_column(String(512))
    docket_url: Mapped[str | None] = mapped_column(Text)
    issue_date: Mapped[date | None] = mapped_column(Date)
    comment_close_date: Mapped[date | None] = mapped_column(Date)
    open_comment: Mapped[bool | None] = mapped_column(Boolean)
    fda_last_changed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceArtifact(Base):
    """Preserved raw-source artifact with filesystem key and audit metadata."""

    __tablename__ = "source_artifacts"
    __table_args__ = (
        Index("ix_source_artifacts_document_slug", "document_slug"),
        Index("ix_source_artifacts_sha256", "sha256"),
        Index("ix_source_artifacts_version_hash", "version_hash"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    storage_backend: Mapped[str] = mapped_column(String(50), nullable=False, default="local")
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    artifact_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    document_slug: Mapped[str | None] = mapped_column(
        String(512),
        ForeignKey("guidance_registry.slug", ondelete="SET NULL"),
    )
    version_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class GuidanceChunk(Base):
    """Dense retrieval chunk stored in PostgreSQL pgvector with citation payload."""

    __tablename__ = "guidance_chunks"
    __table_args__ = (
        Index("ix_guidance_chunks_document_slug", "document_slug"),
        Index("ix_guidance_chunks_version_hash", "version_hash"),
        Index("ix_guidance_chunks_parent_chunk_id", "parent_chunk_id"),
        Index("ix_guidance_chunks_section_id", "section_id"),
    )

    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    document_slug: Mapped[str | None] = mapped_column(
        String(512),
        ForeignKey("guidance_registry.slug", ondelete="SET NULL"),
    )
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_chunk_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    section_id: Mapped[str | None] = mapped_column(String(512))
    section_title: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    char_start: Mapped[int | None] = mapped_column(BigInteger)
    char_end: Mapped[int | None] = mapped_column(BigInteger)
    token_count: Mapped[int | None] = mapped_column(Integer)
    evidence_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AlertStatus(str, Enum):
    """Lifecycle status of an update-monitoring alert record."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class ExportStatus(str, Enum):
    """Lifecycle status of a generated export artifact."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditEventRecord(Base):
    """Persisted audit trail row for queries, answers, refusals, and exports."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_user_id", "user_id"),
        Index("ix_audit_events_session_id", "session_id"),
        Index("ix_audit_events_route", "route"),
        Index("ix_audit_events_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(255))
    session_id: Mapped[str | None] = mapped_column(String(255))
    route: Mapped[str | None] = mapped_column(String(255))
    request_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ChatSessionRecord(Base):
    """Server-owned chat session used for authorization and transcript export."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("ix_chat_sessions_owner_user_id", "owner_user_id"),
        Index("ix_chat_sessions_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ChatTurnRecord(Base):
    """Immutable final answer or refusal recorded for a chat session."""

    __tablename__ = "chat_turns"
    __table_args__ = (
        Index("ix_chat_turns_session_id", "session_id"),
        Index("ix_chat_turns_request_id", "request_id"),
        Index("ix_chat_turns_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str | None] = mapped_column(String(64))
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    refused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    refusal_reason: Mapped[str | None] = mapped_column(Text)
    guardrail_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    provider_name: Mapped[str | None] = mapped_column(String(50))
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GroundedSummaryRecord(Base):
    """Durable grounded summary or version comparison used by exports."""

    __tablename__ = "grounded_summaries"
    __table_args__ = (
        Index("ix_grounded_summaries_owner_user_id", "owner_user_id"),
        Index("ix_grounded_summaries_document_slug", "document_slug"),
        Index("ix_grounded_summaries_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_slug: Mapped[str | None] = mapped_column(
        String(512), ForeignKey("guidance_registry.slug", ondelete="SET NULL")
    )
    summary_type: Mapped[str] = mapped_column(String(30), nullable=False)
    current_version_hash: Mapped[str | None] = mapped_column(String(64))
    previous_version_hash: Mapped[str | None] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    refused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    refusal_reason: Mapped[str | None] = mapped_column(Text)
    guardrail_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    comparison_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AlertRecordORM(Base):
    """Persisted update-monitoring alert for new, updated, or withdrawn guidance."""

    __tablename__ = "alert_records"
    __table_args__ = (
        UniqueConstraint("event_fingerprint", name="uq_alert_records_event_fingerprint"),
        Index("ix_alert_records_document_slug", "document_slug"),
        Index("ix_alert_records_alert_type", "alert_type"),
        Index("ix_alert_records_status", "status"),
        Index("ix_alert_records_detected_at", "detected_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    document_slug: Mapped[str | None] = mapped_column(
        String(512),
        ForeignKey("guidance_registry.slug", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(50))
    current_status: Mapped[str | None] = mapped_column(String(50))
    previous_version_hash: Mapped[str | None] = mapped_column(String(64))
    current_version_hash: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AlertStatus.OPEN.value,
        server_default=AlertStatus.OPEN.value,
    )
    acknowledged_by: Mapped[str | None] = mapped_column(String(255))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ExportRecordORM(Base):
    """Persisted metadata for a generated summary/transcript export artifact."""

    __tablename__ = "export_records"
    __table_args__ = (
        Index("ix_export_records_requested_by", "requested_by"),
        Index("ix_export_records_session_id", "session_id"),
        Index("ix_export_records_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    export_type: Mapped[str] = mapped_column(String(50), nullable=False)
    export_format: Mapped[str] = mapped_column(String(20), nullable=False)
    object_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ExportStatus.PENDING.value,
        server_default=ExportStatus.PENDING.value,
    )
    requested_by: Mapped[str | None] = mapped_column(String(255))
    session_id: Mapped[str | None] = mapped_column(String(255))
    summary_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grounded_summaries.id", ondelete="SET NULL")
    )
    document_slug: Mapped[str | None] = mapped_column(
        String(512),
        ForeignKey("guidance_registry.slug", ondelete="SET NULL"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
