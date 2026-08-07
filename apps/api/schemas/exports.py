"""Export request/result schemas for summaries and chat transcripts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExportKind(str, Enum):
    """Kind of content being exported."""

    SUMMARY = "summary"
    TRANSCRIPT = "transcript"


class ExportFormat(str, Enum):
    """Output file format for an export artifact."""

    DOCX = "docx"
    PDF = "pdf"
    TEXT = "text"


class ExportStatus(str, Enum):
    """Lifecycle status of an export artifact."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportRequest(BaseModel):
    """A request to export a grounded summary or chat transcript."""

    model_config = ConfigDict(extra="forbid")

    export_type: ExportKind
    export_format: ExportFormat = Field(default=ExportFormat.TEXT)
    session_id: str | None = Field(
        default=None, description="Owning session id for transcript exports."
    )
    summary_id: UUID | None = Field(
        default=None, description="Owned summary id for summary exports."
    )


class ExportResult(BaseModel):
    """Metadata describing a generated export artifact."""

    model_config = ConfigDict(extra="forbid")

    export_id: str
    status: ExportStatus
    export_format: ExportFormat
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
