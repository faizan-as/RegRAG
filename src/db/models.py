"""SQLAlchemy models for FDA guidance ingestion metadata."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
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