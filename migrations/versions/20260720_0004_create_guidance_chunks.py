"""Create pgvector guidance chunks table."""

from __future__ import annotations

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260720_0004"
down_revision = "20260720_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "guidance_chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("document_slug", sa.String(length=512), nullable=True),
        sa.Column("version_hash", sa.String(length=64), nullable=False),
        sa.Column("chunk_type", sa.String(length=20), nullable=False),
        sa.Column("parent_chunk_id", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("section_id", sa.String(length=512), nullable=True),
        sa.Column("section_title", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.BigInteger(), nullable=True),
        sa.Column("char_end", sa.BigInteger(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_slug"], ["guidance_registry.slug"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("chunk_id"),
    )
    op.create_index("ix_guidance_chunks_document_slug", "guidance_chunks", ["document_slug"])
    op.create_index("ix_guidance_chunks_parent_chunk_id", "guidance_chunks", ["parent_chunk_id"])
    op.create_index("ix_guidance_chunks_section_id", "guidance_chunks", ["section_id"])
    op.create_index("ix_guidance_chunks_version_hash", "guidance_chunks", ["version_hash"])
    op.create_index(
        "ix_guidance_chunks_embedding_hnsw",
        "guidance_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Revert migration."""
    op.drop_index("ix_guidance_chunks_embedding_hnsw", table_name="guidance_chunks")
    op.drop_index("ix_guidance_chunks_version_hash", table_name="guidance_chunks")
    op.drop_index("ix_guidance_chunks_section_id", table_name="guidance_chunks")
    op.drop_index("ix_guidance_chunks_parent_chunk_id", table_name="guidance_chunks")
    op.drop_index("ix_guidance_chunks_document_slug", table_name="guidance_chunks")
    op.drop_table("guidance_chunks")