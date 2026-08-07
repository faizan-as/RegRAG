"""Create audit_events, alert_records, and export_records tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260730_0005"
down_revision = "20260720_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("route", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_session_id", "audit_events", ["session_id"])
    op.create_index("ix_audit_events_route", "audit_events", ["route"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    op.create_table(
        "alert_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_type", sa.String(length=20), nullable=False),
        sa.Column("document_slug", sa.String(length=512), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.String(length=50), nullable=True),
        sa.Column("current_status", sa.String(length=50), nullable=True),
        sa.Column("previous_version_hash", sa.String(length=64), nullable=True),
        sa.Column("current_version_hash", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("acknowledged_by", sa.String(length=255), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_slug"], ["guidance_registry.slug"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_records_document_slug", "alert_records", ["document_slug"])
    op.create_index("ix_alert_records_alert_type", "alert_records", ["alert_type"])
    op.create_index("ix_alert_records_status", "alert_records", ["status"])
    op.create_index("ix_alert_records_detected_at", "alert_records", ["detected_at"])

    op.create_table(
        "export_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(length=50), nullable=False),
        sa.Column("export_format", sa.String(length=20), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("document_slug", sa.String(length=512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_slug"], ["guidance_registry.slug"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_records_requested_by", "export_records", ["requested_by"])
    op.create_index("ix_export_records_session_id", "export_records", ["session_id"])
    op.create_index("ix_export_records_created_at", "export_records", ["created_at"])


def downgrade() -> None:
    """Revert migration."""
    op.drop_index("ix_export_records_created_at", table_name="export_records")
    op.drop_index("ix_export_records_session_id", table_name="export_records")
    op.drop_index("ix_export_records_requested_by", table_name="export_records")
    op.drop_table("export_records")

    op.drop_index("ix_alert_records_detected_at", table_name="alert_records")
    op.drop_index("ix_alert_records_status", table_name="alert_records")
    op.drop_index("ix_alert_records_alert_type", table_name="alert_records")
    op.drop_index("ix_alert_records_document_slug", table_name="alert_records")
    op.drop_table("alert_records")

    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_route", table_name="audit_events")
    op.drop_index("ix_audit_events_session_id", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_table("audit_events")
