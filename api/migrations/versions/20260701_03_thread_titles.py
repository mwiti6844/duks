"""semantic conversation title metadata

Revision ID: 20260701_03
Revises: 20260701_02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260701_03"
down_revision = "20260701_02"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "conversation_threads" not in inspector.get_table_names():
        return
    columns = {
        column["name"] for column in inspector.get_columns("conversation_threads")
    }
    if "title_locked" not in columns:
        with op.batch_alter_table("conversation_threads") as batch:
            batch.add_column(sa.Column(
                "title_locked", sa.Boolean(), nullable=False, server_default=sa.false()
            ))


def downgrade():
    with op.batch_alter_table("conversation_threads") as batch:
        batch.drop_column("title_locked")
