"""Chunk and embedding models for parent-child ingestion."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ChunkType(str, Enum):
    """Granularity of a chunk in the parent-child hierarchy."""

    PARENT = "parent"
    CHILD = "child"


class Chunk(BaseModel):
    """A section-level (parent) or paragraph-level (child) text chunk."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(description="Stable unique chunk identifier.")
    document_id: str = Field(description="Owning document identifier.")
    chunk_type: ChunkType = Field(description="Parent or child granularity.")
    parent_chunk_id: str | None = Field(
        default=None, description="Parent chunk id for child chunks."
    )
    text: str = Field(description="Chunk text content.")
    version_hash: str | None = Field(
        default=None, description="SHA-256 version hash for the source document."
    )
    source_url: str | None = Field(
        default=None, description="Source FDA URL used for citation resolution."
    )
    section_id: str | None = Field(default=None, description="Normalized section identifier.")
    section_title: str | None = Field(default=None, description="Human-readable section heading.")
    page_number: int | None = Field(default=None, ge=0, description="Source PDF page number.")
    char_start: int | None = Field(
        default=None, ge=0, description="Inclusive character offset in parsed document text."
    )
    char_end: int | None = Field(
        default=None, ge=0, description="Exclusive character offset in parsed document text."
    )
    token_count: int | None = Field(
        default=None, ge=0, description="Approximate token count of the chunk."
    )


class EmbeddedChunk(BaseModel):
    """A chunk paired with its dense embedding vector."""

    model_config = ConfigDict(extra="forbid")

    chunk: Chunk = Field(description="The source chunk.")
    embedding: list[float] = Field(description="Dense embedding vector (BGE-M3).")
    embedding_model: str = Field(description="Model that produced the embedding.")
