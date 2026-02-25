"""Add website_visits table for tracking page visits

Revision ID: 010_add_website_visits
Revises: 009_add_analytics_metrics
Create Date: 2026-01-28 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "010_add_website_visits"
down_revision = "009_add_analytics_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_visits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("page_url", sa.String(length=500), nullable=False),
        sa.Column("referrer", sa.String(length=500), nullable=True),
        sa.Column("device_type", sa.String(length=50), nullable=True),
        sa.Column("browser", sa.String(length=100), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("is_bounce", sa.String(length=10), nullable=True, server_default='unknown'),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Внешние ключи
    op.create_foreign_key(
        "fk_website_visits_session_id",
        "website_visits", "sessions",
        ["session_id"], ["id"],
        ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_website_visits_user_id",
        "website_visits", "users",
        ["user_id"], ["id"],
        ondelete="SET NULL"
    )
    
    # Индексы
    op.create_index("ix_website_visits_session_id", "website_visits", ["session_id"])
    op.create_index("ix_website_visits_user_id", "website_visits", ["user_id"])
    op.create_index("ix_website_visits_page_url", "website_visits", ["page_url"])
    op.create_index("ix_website_visits_created_at", "website_visits", ["created_at"])
    op.create_index("ix_website_visits_user_created", "website_visits", ["user_id", "created_at"])
    op.create_index("ix_website_visits_session_created", "website_visits", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_website_visits_session_created", "website_visits")
    op.drop_index("ix_website_visits_user_created", "website_visits")
    op.drop_index("ix_website_visits_created_at", "website_visits")
    op.drop_index("ix_website_visits_page_url", "website_visits")
    op.drop_index("ix_website_visits_user_id", "website_visits")
    op.drop_index("ix_website_visits_session_id", "website_visits")
    op.drop_constraint("fk_website_visits_user_id", "website_visits", type_="foreignkey")
    op.drop_constraint("fk_website_visits_session_id", "website_visits", type_="foreignkey")
    op.drop_table("website_visits")
