"""Add user_id to content_plans table for multitenancy

Revision ID: 013_add_user_to_content_plans
Revises: 012_add_user_password
Create Date: 2026-01-28 17:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "013_add_user_to_content_plans"
down_revision = "012_add_user_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_plans", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_content_plans_user_id",
        "content_plans", "users",
        ["user_id"], ["id"],
        ondelete="CASCADE"
    )
    op.create_index("ix_content_plans_user_id", "content_plans", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_content_plans_user_id", "content_plans")
    op.drop_constraint("fk_content_plans_user_id", "content_plans", type_="foreignkey")
    op.drop_column("content_plans", "user_id")
