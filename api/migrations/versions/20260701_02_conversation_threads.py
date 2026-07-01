"""durable conversation threads and replayable messages

Revision ID: 20260701_02
Revises: 20260630_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260701_02"
down_revision = "20260630_01"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "conversation_threads" not in tables:
        op.create_table(
            "conversation_threads",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(), nullable=False, server_default="New conversation"),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_conversation_threads_user_id", "conversation_threads", ["user_id"])
        op.create_index("ix_conversation_threads_status", "conversation_threads", ["status"])
        op.create_index("ix_conversation_threads_updated_at", "conversation_threads", ["updated_at"])
        op.create_index(
            "ix_conversation_threads_last_message_at",
            "conversation_threads",
            ["last_message_at"],
        )

    if "conversation_messages" not in tables:
        op.create_table(
            "conversation_messages",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "thread_id", sa.String(),
                sa.ForeignKey("conversation_threads.id"), nullable=False,
            ),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="complete"),
            sa.Column("sequence_number", sa.Integer(), nullable=False),
            sa.Column("content_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("trace_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("tools_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "thread_id", "sequence_number", name="uq_thread_message_sequence"
            ),
        )
        op.create_index(
            "ix_conversation_messages_thread_id",
            "conversation_messages",
            ["thread_id"],
        )
        op.create_index(
            "ix_conversation_messages_user_id",
            "conversation_messages",
            ["user_id"],
        )


def downgrade():
    op.drop_table("conversation_messages")
    op.drop_table("conversation_threads")
