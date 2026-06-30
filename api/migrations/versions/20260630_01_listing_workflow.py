"""durable guided listing workflow

Revision ID: 20260630_01
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20260630_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "used_car_listings" in tables:
        columns = {item["name"] for item in inspector.get_columns("used_car_listings")}
        with op.batch_alter_table("used_car_listings") as batch:
            if "version" not in columns:
                batch.add_column(sa.Column("version", sa.Integer(), nullable=False,
                                           server_default="1"))
            if "published_at" not in columns:
                batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True)))
            if "updated_at" not in columns:
                batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True)))

    if "listing_drafts" not in tables:
        op.create_table(
            "listing_drafts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("mode", sa.String(), nullable=False, server_default="create"),
            sa.Column("target_listing_id", sa.String(),
                      sa.ForeignKey("used_car_listings.id")),
            sa.Column("status", sa.String(), nullable=False, server_default="collecting"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("fields_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("validation_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("guidance_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
        )
        op.create_index("ix_listing_drafts_owner_id", "listing_drafts", ["owner_id"])
        op.create_index("ix_listing_drafts_status", "listing_drafts", ["status"])

    if "listing_images" not in tables:
        op.create_table(
            "listing_images",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("draft_id", sa.String(), sa.ForeignKey("listing_drafts.id")),
            sa.Column("listing_id", sa.String(), sa.ForeignKey("used_car_listings.id")),
            sa.Column("cloudinary_public_id", sa.String(), unique=True, nullable=False),
            sa.Column("secure_url", sa.String(), nullable=False),
            sa.Column("width", sa.Integer()),
            sa.Column("height", sa.Integer()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        )

    if "listing_mutations" not in tables:
        op.create_table(
            "listing_mutations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("draft_id", sa.String(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("listing_id", sa.String(),
                      sa.ForeignKey("used_car_listings.id"), nullable=False),
            sa.Column("operation", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("draft_id", "revision",
                                name="uq_listing_mutation_revision"),
        )


def downgrade():
    op.drop_table("listing_mutations")
    op.drop_table("listing_images")
    op.drop_table("listing_drafts")
