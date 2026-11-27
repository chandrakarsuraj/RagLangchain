"""Create document, feedback, audit, approval, and chat tables.

Revision ID: 20261127_0001
Revises:
Create Date: 2026-11-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261127_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("owner_sub", sa.Text(), nullable=False),
        sa.Column("allowed_groups", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed', 'retired')",
            name="documents_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="documents_pkey"),
        sa.UniqueConstraint("s3_key", name="documents_s3_key_key"),
    )
    op.create_index("documents_acl_idx", "documents", ["tenant_id", "status"], unique=False)

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("rating BETWEEN -1 AND 1", name="feedback_rating_check"),
        sa.PrimaryKeyConstraint("id", name="feedback_pkey"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="audit_events_pkey"),
    )
    op.create_index(
        "audit_tenant_time",
        "audit_events",
        ["tenant_id", sa.text("created_at DESC")],
        unique=False,
    )

    op.create_table(
        "approvals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("requester", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("reviewer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="approvals_pkey"),
    )
    op.create_index("approvals_tenant_idx", "approvals", ["tenant_id", "status"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="chat_messages_role_check"),
        sa.PrimaryKeyConstraint("id", name="chat_messages_pkey"),
    )
    op.create_index(
        "chat_messages_session_idx",
        "chat_messages",
        ["tenant_id", "conversation_id", sa.text("id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("chat_messages_session_idx", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("approvals_tenant_idx", table_name="approvals")
    op.drop_table("approvals")

    op.drop_index("audit_tenant_time", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_table("feedback")

    op.drop_index("documents_acl_idx", table_name="documents")
    op.drop_table("documents")
