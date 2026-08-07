"""Grounded summary, key-requirement, and key-change schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from apps.api.schemas.evidence import EvidenceCard


class SummaryType(str, Enum):
    """Kind of grounded summarization output."""

    SUMMARY = "summary"
    KEY_REQUIREMENTS = "key_requirements"
    KEY_CHANGES = "key_changes"


class SummaryRequest(BaseModel):
    """A request to summarize a guidance document from grounded evidence."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(description="Stable internal FDA document identifier.")
    summary_type: SummaryType = Field(default=SummaryType.SUMMARY)
    compare_version_hash: str | None = Field(
        default=None,
        description="Prior version hash to diff against for key_changes summaries.",
    )


class SummaryResult(BaseModel):
    """A grounded summary/key-requirement/key-change result."""

    model_config = ConfigDict(extra="forbid")

    summary_id: str | None = Field(default=None, description="Durable server-owned summary id.")
    document_id: str = Field(description="Stable internal FDA document identifier.")
    summary_type: SummaryType
    text: str = Field(description="Generated summary text with inline citation markers.")
    evidence: list[EvidenceCard] = Field(default_factory=list)
    refused: bool = Field(default=False)
    refusal_reason: str | None = Field(default=None)
    current_version_hash: str | None = None
    previous_version_hash: str | None = None
    faithfulness_passed: bool | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
