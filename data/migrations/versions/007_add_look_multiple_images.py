"""Add support for multiple images per look

Revision ID: 007_add_look_multiple_images
Revises: 006_add_look_generation_fields
Create Date: 2026-01-29 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007_add_look_multiple_images"
down_revision = "006_add_look_generation_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поля для поддержки нескольких изображений
    op.add_column("looks", sa.Column("image_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("looks", sa.Column("current_image_index", sa.Integer(), nullable=True))
    
    # Заполняем image_urls существующими image_url для обратной совместимости
    op.execute("""
        UPDATE looks 
        SET image_urls = CASE 
            WHEN image_url IS NOT NULL THEN jsonb_build_array(image_url)
            ELSE '[]'::jsonb
        END,
        current_image_index = CASE 
            WHEN image_url IS NOT NULL THEN 0
            ELSE NULL
        END
    """)


def downgrade() -> None:
    # Восстанавливаем image_url из первого элемента image_urls перед удалением
    op.execute("""
        UPDATE looks 
        SET image_url = CASE 
            WHEN image_urls IS NOT NULL AND jsonb_array_length(image_urls) > 0 
            THEN image_urls->0->>'url'
            ELSE NULL
        END
    """)
    
    # Удаляем колонки
    op.drop_column("looks", "current_image_index")
    op.drop_column("looks", "image_urls")
