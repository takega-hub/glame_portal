"""add background image to home slides

Revision ID: 044_home_slide_background_image
Revises: 043_look_is_new
Create Date: 2026-05-08 23:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "044_home_slide_background_image"
down_revision = "043_look_is_new"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_home_slides",
        sa.Column("background_image_url", sa.String(length=500), nullable=True),
    )
    op.execute(
        """
        INSERT INTO app_home_slides (
            id,
            block_key,
            title,
            subtitle,
            background_image_url,
            image_url,
            sort_order,
            is_active
        )
        SELECT
            '7e2f8c4f-bf07-4db3-a5f1-5f9de063fb44'::uuid,
            'collected_glame',
            'Собрано GLAME',
            'Мы отбираем главное.\nЧтобы вы выбирали свое.',
            '/static/app_admin_media/home_block4_background_underlay.png',
            '/static/app_admin_media/home_block4_visual_image_no_text.png',
            0,
            TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM app_home_slides WHERE block_key = 'collected_glame'
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM app_home_slides
        WHERE id = '7e2f8c4f-bf07-4db3-a5f1-5f9de063fb44'::uuid
        """
    )
    op.drop_column("app_home_slides", "background_image_url")
