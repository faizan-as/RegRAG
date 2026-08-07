"""Add API sessions, turns, summaries, and alert fingerprints."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260805_0006"
down_revision = "20260730_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration."""
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_owner_user_id", "chat_sessions", ["owner_user_id"])
    op.create_index("ix_chat_sessions_created_at", "chat_sessions", ["created_at"])

    op.create_table(
        "chat_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("refused", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("guardrail_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_name", sa.String(length=50), nullable=True),
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_turns_session_id", "chat_turns", ["session_id"])
    op.create_index("ix_chat_turns_request_id", "chat_turns", ["request_id"])
    op.create_index("ix_chat_turns_created_at", "chat_turns", ["created_at"])

    op.create_table(
        "grounded_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("document_slug", sa.String(length=512), nullable=True),
        sa.Column("summary_type", sa.String(length=30), nullable=False),
        sa.Column("current_version_hash", sa.String(length=64), nullable=True),
        sa.Column("previous_version_hash", sa.String(length=64), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("refused", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("guardrail_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("comparison_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_slug"], ["guidance_registry.slug"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_grounded_summaries_owner_user_id", "grounded_summaries", ["owner_user_id"])
    op.create_index("ix_grounded_summaries_document_slug", "grounded_summaries", ["document_slug"])
    op.create_index("ix_grounded_summaries_created_at", "grounded_summaries", ["created_at"])

    op.add_column(
        "alert_records", sa.Column("event_fingerprint", sa.String(length=64), nullable=True)
    )
    op.execute("""
        UPDATE alert_records
        SET event_fingerprint = md5(id::text || ':' || alert_type || ':' || COALESCE(document_slug, ''))
            || md5(COALESCE(document_slug, '') || ':' || alert_type || ':' || id::text)
        """)
    op.alter_column("alert_records", "event_fingerprint", nullable=False)
    op.create_unique_constraint(
        "uq_alert_records_event_fingerprint", "alert_records", ["event_fingerprint"]
    )

    op.add_column(
        "export_records", sa.Column("summary_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_export_records_summary_id_grounded_summaries",
        "export_records",
        "grounded_summaries",
        ["summary_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Revert migration."""
    op.drop_constraint(
        "fk_export_records_summary_id_grounded_summaries", "export_records", type_="foreignkey"
    )
    op.drop_column("export_records", "summary_id")
    op.drop_constraint("uq_alert_records_event_fingerprint", "alert_records", type_="unique")
    op.drop_column("alert_records", "event_fingerprint")
    op.drop_index("ix_grounded_summaries_created_at", table_name="grounded_summaries")
    op.drop_index("ix_grounded_summaries_document_slug", table_name="grounded_summaries")
    op.drop_index("ix_grounded_summaries_owner_user_id", table_name="grounded_summaries")
    op.drop_table("grounded_summaries")
    op.drop_index("ix_chat_turns_created_at", table_name="chat_turns")
    op.drop_index("ix_chat_turns_request_id", table_name="chat_turns")
    op.drop_index("ix_chat_turns_session_id", table_name="chat_turns")
    op.drop_table("chat_turns")
    op.drop_index("ix_chat_sessions_created_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_owner_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
