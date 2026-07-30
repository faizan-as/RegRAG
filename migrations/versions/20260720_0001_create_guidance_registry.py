"""Create guidance registry."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260720_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    lifecycle_state = postgresql.ENUM(
        "active",
        "withdrawn",
        name="lifecycle_state",
        create_type=False,
    )
    lifecycle_state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "guidance_registry",
        sa.Column("slug", sa.String(length=512), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("landing_url", sa.Text(), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("lifecycle_state", lifecycle_state, server_default="active", nullable=False),
        sa.Column("center", sa.String(length=100), nullable=True),
        sa.Column("communication_type", sa.String(length=255), nullable=True),
        sa.Column("topics", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("regulated_product", sa.String(length=255), nullable=True),
        sa.Column("docket_id", sa.String(length=100), nullable=True),
        sa.Column("docket_url", sa.Text(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("comment_close_date", sa.Date(), nullable=True),
        sa.Column("open_comment", sa.Boolean(), nullable=True),
        sa.Column("fda_last_changed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("slug"),
    )
    op.create_index("ix_guidance_registry_center", "guidance_registry", ["center"])
    op.create_index("ix_guidance_registry_docket_id", "guidance_registry", ["docket_id"])
    op.create_index(
        "ix_guidance_registry_fda_last_changed",
        "guidance_registry",
        ["fda_last_changed"],
    )
    op.create_index(
        "ix_guidance_registry_lifecycle_state",
        "guidance_registry",
        ["lifecycle_state"],
    )
    op.create_index("ix_guidance_registry_status", "guidance_registry", ["status"])


def downgrade() -> None:
    """Revert migration."""
    op.drop_index("ix_guidance_registry_status", table_name="guidance_registry")
    op.drop_index("ix_guidance_registry_lifecycle_state", table_name="guidance_registry")
    op.drop_index("ix_guidance_registry_fda_last_changed", table_name="guidance_registry")
    op.drop_index("ix_guidance_registry_docket_id", table_name="guidance_registry")
    op.drop_index("ix_guidance_registry_center", table_name="guidance_registry")
    op.drop_table("guidance_registry")

    lifecycle_state = postgresql.ENUM(
        "active",
        "withdrawn",
        name="lifecycle_state",
        create_type=False,
    )
    lifecycle_state.drop(op.get_bind(), checkfirst=True)