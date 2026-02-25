"""Add marketing_campaigns table

Revision ID: 014_add_marketing_campaigns
Revises: 013_add_user_to_content_plans
Create Date: 2026-01-28 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = "014_add_marketing_campaigns"
down_revision = "013_add_user_to_content_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default='draft'),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("target_audience", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("channels", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("content_plan_id", UUID(as_uuid=True), nullable=True),
        sa.Column("metrics", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    
    # Внешние ключи
    op.create_foreign_key(
        "fk_marketing_campaigns_user_id",
        "marketing_campaigns", "users",
        ["user_id"], ["id"],
        ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_marketing_campaigns_content_plan_id",
        "marketing_campaigns", "content_plans",
        ["content_plan_id"], ["id"],
        ondelete="SET NULL"
    )
    
    # Индексы
    op.create_index("ix_marketing_campaigns_user_id", "marketing_campaigns", ["user_id"])
    op.create_index("ix_marketing_campaigns_content_plan_id", "marketing_campaigns", ["content_plan_id"])
    op.create_index("ix_marketing_campaigns_status", "marketing_campaigns", ["status"])


def downgrade() -> None:
    op.drop_index("ix_marketing_campaigns_status", "marketing_campaigns")
    op.drop_index("ix_marketing_campaigns_content_plan_id", "marketing_campaigns")
    op.drop_index("ix_marketing_campaigns_user_id", "marketing_campaigns")
    op.drop_constraint("fk_marketing_campaigns_content_plan_id", "marketing_campaigns", type_="foreignkey")
    op.drop_constraint("fk_marketing_campaigns_user_id", "marketing_campaigns", type_="foreignkey")
    op.drop_table("marketing_campaigns")
