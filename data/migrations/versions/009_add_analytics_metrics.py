"""Add analytics_metrics table for pre-calculated metrics

Revision ID: 009_add_analytics_metrics
Revises: 008_expand_analytics_events
Create Date: 2026-01-28 13:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "009_add_analytics_metrics"
down_revision = "008_expand_analytics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("metric_type", sa.String(length=50), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(15, 2), nullable=False),
        sa.Column("dimensions", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    
    # Индексы
    op.create_index("ix_analytics_metrics_metric_type", "analytics_metrics", ["metric_type"])
    op.create_index("ix_analytics_metrics_period", "analytics_metrics", ["period"])
    op.create_index("ix_analytics_metrics_period_start", "analytics_metrics", ["period_start"])
    op.create_index("ix_analytics_metrics_type_period", "analytics_metrics", ["metric_type", "period", "period_start"])


def downgrade() -> None:
    op.drop_index("ix_analytics_metrics_type_period", "analytics_metrics")
    op.drop_index("ix_analytics_metrics_period_start", "analytics_metrics")
    op.drop_index("ix_analytics_metrics_period", "analytics_metrics")
    op.drop_index("ix_analytics_metrics_metric_type", "analytics_metrics")
    op.drop_table("analytics_metrics")
