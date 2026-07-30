"""Create source artifacts metadata table."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260720_0002"
down_revision = "20260720_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""
    op.create_table(
        "source_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_backend", sa.String(length=50), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("artifact_kind", sa.String(length=50), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("document_slug", sa.String(length=512), nullable=True),
        sa.Column("version_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_slug"], ["guidance_registry.slug"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_source_artifacts_document_slug", "source_artifacts", ["document_slug"])
    op.create_index("ix_source_artifacts_sha256", "source_artifacts", ["sha256"])
    op.create_index("ix_source_artifacts_version_hash", "source_artifacts", ["version_hash"])


def downgrade() -> None:
    """Revert migration."""
    op.drop_index("ix_source_artifacts_version_hash", table_name="source_artifacts")
    op.drop_index("ix_source_artifacts_sha256", table_name="source_artifacts")
    op.drop_index("ix_source_artifacts_document_slug", table_name="source_artifacts")
    op.drop_table("source_artifacts")