"""Widen guidance registry catalog fields."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260720_0003"
down_revision = "20260720_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""
    op.alter_column(
        "guidance_registry",
        "regulated_product",
        existing_type=sa.String(length=255),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
    op.alter_column(
        "guidance_registry",
        "docket_id",
        existing_type=sa.String(length=100),
        type_=sa.String(length=512),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Revert migration."""
    op.alter_column(
        "guidance_registry",
        "docket_id",
        existing_type=sa.String(length=512),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "guidance_registry",
        "regulated_product",
        existing_type=sa.String(length=512),
        type_=sa.String(length=255),
        existing_nullable=True,
    )