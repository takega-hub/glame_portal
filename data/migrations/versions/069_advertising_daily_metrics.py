"""Store daily read-only advertising performance facts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "069_advertising_daily_metrics"
down_revision = "068_marketing_campaign_yandex_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "advertising_daily_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("advertising_connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("marketing_campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_campaign_id", sa.String(length=128), nullable=False),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
        sa.Column("raw_metrics", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["advertising_connection_id"], ["advertising_connections.id"]),
        sa.ForeignKeyConstraint(["marketing_campaign_id"], ["marketing_campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("advertising_connection_id", "external_campaign_id", "metric_date", name="uq_advertising_daily_metrics_connection_campaign_date"),
    )
    op.create_index("ix_advertising_daily_metrics_connection", "advertising_daily_metrics", ["advertising_connection_id"])
    op.create_index("ix_advertising_daily_metrics_campaign", "advertising_daily_metrics", ["marketing_campaign_id"])
    op.create_index("ix_advertising_daily_metrics_external_campaign", "advertising_daily_metrics", ["external_campaign_id"])
    op.create_index("ix_advertising_daily_metrics_date", "advertising_daily_metrics", ["metric_date"])


def downgrade():
    op.drop_index("ix_advertising_daily_metrics_date", table_name="advertising_daily_metrics")
    op.drop_index("ix_advertising_daily_metrics_external_campaign", table_name="advertising_daily_metrics")
    op.drop_index("ix_advertising_daily_metrics_campaign", table_name="advertising_daily_metrics")
    op.drop_index("ix_advertising_daily_metrics_connection", table_name="advertising_daily_metrics")
    op.drop_table("advertising_daily_metrics")
