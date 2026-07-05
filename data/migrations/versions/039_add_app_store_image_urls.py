"""add app store image urls

Revision ID: 039_add_app_store_image_urls
Revises: 038_add_look_multi_value_fields
Create Date: 2026-05-05 12:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "039_add_app_store_image_urls"
down_revision = "038_add_look_multi_value_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_stores", sa.Column("image_urls", sa.JSON(), nullable=True))
    op.execute(
        """
        UPDATE app_stores
        SET image_urls = CASE
            WHEN image_url IS NOT NULL AND btrim(image_url) <> '' THEN to_json(ARRAY[image_url])
            ELSE '[]'::json
        END
        """
    )


def downgrade() -> None:
    op.drop_column("app_stores", "image_urls")
