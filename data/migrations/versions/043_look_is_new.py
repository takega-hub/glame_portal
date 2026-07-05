"""add is_new flag to looks

Revision ID: 043_look_is_new
Revises: 042_home_slide_image_action
Create Date: 2026-05-07 13:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "043_look_is_new"
down_revision = "042_home_slide_image_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "looks",
        sa.Column("is_new", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_looks_is_new", "looks", ["is_new"], unique=False)
    op.alter_column("looks", "is_new", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_looks_is_new", table_name="looks")
    op.drop_column("looks", "is_new")
