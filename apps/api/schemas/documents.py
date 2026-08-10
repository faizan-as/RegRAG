"""Document and metadata models for FDA guidance sources."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from src.db.models import LifecycleState


class DocumentStatus(str, Enum):
    """Lifecycle status of an FDA guidance document."""

    DRAFT = "Draft"
    FINAL = "Final"
    WITHDRAWN = "Withdrawn"


class DocumentMetadata(BaseModel):
    """Metadata describing a single FDA guidance document version."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(description="Stable internal FDA document identifier.")
    title: str = Field(description="FDA guidance title.")
    source_url: HttpUrl = Field(description="Canonical FDA source URL.")
    status: DocumentStatus = Field(description="Draft, Final, or Withdrawn.")
    version_hash: str = Field(description="SHA-256 hash of the source document version.")
    docket_number: str | None = Field(default=None, description="FDA docket number when available.")
    docket_url: HttpUrl | None = Field(default=None, description="FDA docket URL when available.")
    issuing_office: str | None = Field(default=None, description="Issuing FDA center or office.")
    center: str | None = Field(default=None, description="FDA center from the catalog.")
    topic: str | None = Field(default=None, description="Primary FDA guidance topic.")
    topics: list[str] = Field(
        default_factory=list, description="All FDA guidance topics from the catalog."
    )
    communication_type: str | None = Field(
        default=None, description="FDA communication type from the catalog."
    )
    regulated_product: str | None = Field(
        default=None, description="Regulated product category from the FDA catalog."
    )
    published_date: datetime | None = Field(default=None, description="Original publication date.")
    issue_date: date | None = Field(default=None, description="FDA issue date.")
    fda_last_changed: datetime | None = Field(
        default=None, description="FDA catalog changed timestamp."
    )
    comment_close: date | None = Field(
        default=None, description="Comment close date for draft guidance."
    )
    open_comment: bool | None = Field(
        default=None, description="Whether the FDA catalog marks comments as open."
    )
    lifecycle_state: LifecycleState = Field(
        default=LifecycleState.ACTIVE,
        description="Registry lifecycle state derived from catalog diffs.",
    )
    last_updated: datetime | None = Field(default=None, description="Most recent FDA update date.")
    cfr_references: list[str] = Field(
        default_factory=list, description="CFR references identified for metadata filters."
    )
    product_codes: list[str] = Field(
        default_factory=list, description="FDA product codes identified for metadata filters."
    )
    page_count: int | None = Field(
        default=None, ge=0, description="Number of pages in the source PDF."
    )
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the document was ingested.",
    )


class DocumentVersion(BaseModel):
    """Version snapshot metadata for a preserved FDA source document."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(description="Stable internal FDA document identifier.")
    version_hash: str = Field(description="SHA-256 hash of the source document version.")
    source_url: HttpUrl = Field(description="PDF or landing-page URL for this version.")
    raw_object_key: str = Field(description="Object-store key for the preserved source file.")
    status: DocumentStatus = Field(description="Draft, Final, or Withdrawn.")
    lifecycle_state: LifecycleState = Field(
        default=LifecycleState.ACTIVE,
        description="Registry lifecycle state when this version was recorded.",
    )
    fda_last_changed: datetime | None = Field(
        default=None, description="FDA catalog changed timestamp for this version."
    )
    supersedes_version_hash: str | None = Field(
        default=None, description="Prior version hash superseded by this version."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when this version snapshot was created.",
    )


class DocumentVersionResponse(BaseModel):
    """Public version metadata without internal storage coordinates."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    version_hash: str
    source_url: HttpUrl
    status: DocumentStatus
    lifecycle_state: LifecycleState = LifecycleState.ACTIVE
    fda_last_changed: datetime | None = None
    supersedes_version_hash: str | None = None
    created_at: datetime


class DocumentArtifact(BaseModel):
    """Authorized source artifact descriptor without internal storage paths."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID = Field(description="Identifier accepted by the protected download route.")
    content_type: str = Field(description="Artifact media type.")
    artifact_kind: str = Field(description="Preserved source artifact category.")
    version_hash: str | None = Field(default=None, description="Associated source version hash.")
    size_bytes: int = Field(ge=0, description="Artifact size in bytes.")
    created_at: datetime = Field(description="Artifact preservation timestamp.")


class GuidanceDocument(BaseModel):
    """A parsed FDA guidance document with preserved structure."""

    model_config = ConfigDict(extra="forbid")

    metadata: DocumentMetadata = Field(description="Document-level metadata.")
    versions: list[DocumentVersionResponse] = Field(
        default_factory=list,
        description="Known preserved source versions for this document.",
    )
    section_ids: list[str] = Field(
        default_factory=list,
        description="Ordered normalized section identifiers in the document.",
    )
    artifacts: list[DocumentArtifact] = Field(
        default_factory=list,
        description="Authorized preserved-source descriptors for this document.",
    )


class SectionNavigationEntry(BaseModel):
    """A single section entry for document section-tree navigation."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Normalized section identifier.")
    section_title: str | None = Field(default=None, description="Human-readable section heading.")
    page_number: int | None = Field(
        default=None, ge=0, description="First page number for this section."
    )


class PassageResponse(BaseModel):
    """A single cited passage resolved from a chunk id."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(description="Stable internal FDA document identifier.")
    chunk_id: str = Field(description="Stable unique chunk identifier.")
    section_id: str | None = Field(default=None, description="Normalized section identifier.")
    section_title: str | None = Field(default=None, description="Human-readable section heading.")
    page_number: int | None = Field(default=None, ge=0, description="Source PDF page number.")
    text: str = Field(description="Exact passage text.")
    source_url: HttpUrl = Field(description="FDA source URL.")
    version_hash: str = Field(description="SHA-256 hash of the source document version.")
