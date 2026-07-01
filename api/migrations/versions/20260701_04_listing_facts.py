"""rich catalogue facts and image galleries

Revision ID: 20260701_04
Revises: 20260701_03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260701_04"
down_revision = "20260701_03"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "used_car_listings" in tables:
        columns = {item["name"] for item in inspector.get_columns("used_car_listings")}
        additions = (
            ("trim", sa.String()),
            ("color", sa.String()),
            ("engine_cc", sa.Integer()),
            ("monthly_payment_kes", sa.Integer()),
            ("finance_term_months", sa.Integer()),
            ("seller_name", sa.String()),
            ("location_detail", sa.String()),
            ("source_listing_id", sa.String()),
            ("source_url", sa.String()),
            ("grade_code", sa.String()),
            ("specs_json", sa.Text(), "{}", False),
        )
        with op.batch_alter_table("used_car_listings") as batch:
            for item in additions:
                name, column_type, *rest = item
                if name in columns:
                    continue
                default = rest[0] if rest else None
                nullable = rest[1] if len(rest) > 1 else True
                batch.add_column(sa.Column(
                    name, column_type, nullable=nullable,
                    server_default=default,
                ))
        indexes = {item["name"] for item in inspector.get_indexes("used_car_listings")}
        if "ix_used_car_listings_source_listing_id" not in indexes:
            op.create_index(
                "ix_used_car_listings_source_listing_id",
                "used_car_listings",
                ["source_listing_id"],
            )

    if "used_car_images" not in tables:
        op.create_table(
            "used_car_images",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "listing_id", sa.String(),
                sa.ForeignKey("used_car_listings.id"), nullable=False,
            ),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(), nullable=False, server_default="carduka"),
            sa.UniqueConstraint(
                "listing_id", "sort_order", name="uq_used_car_image_order"
            ),
        )
        op.create_index("ix_used_car_images_listing_id", "used_car_images", ["listing_id"])


def downgrade():
    op.drop_table("used_car_images")
    with op.batch_alter_table("used_car_listings") as batch:
        for name in (
            "specs_json", "grade_code", "source_url", "source_listing_id",
            "location_detail", "seller_name", "finance_term_months",
            "monthly_payment_kes", "engine_cc", "color", "trim",
        ):
            batch.drop_column(name)
