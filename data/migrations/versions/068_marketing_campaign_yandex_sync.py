"""Store external campaign identity for advertising connector imports."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "068_marketing_campaign_yandex_sync"
down_revision = "067_advertising_connections"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("marketing_campaigns", sa.Column("external_source", sa.String(64), nullable=True))
    op.add_column("marketing_campaigns", sa.Column("external_id", sa.String(128), nullable=True))
    op.add_column(
        "marketing_campaigns",
        sa.Column("advertising_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("advertising_connections.id"), nullable=True),
    )
    op.create_index("ix_marketing_campaigns_external_source", "marketing_campaigns", ["external_source"])
    op.create_index("ix_marketing_campaigns_advertising_connection_id", "marketing_campaigns", ["advertising_connection_id"])
    op.create_index(
        "ux_marketing_campaigns_connection_external_id",
        "marketing_campaigns",
        ["advertising_connection_id", "external_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ux_marketing_campaigns_connection_external_id", table_name="marketing_campaigns")
    op.drop_index("ix_marketing_campaigns_advertising_connection_id", table_name="marketing_campaigns")
    op.drop_index("ix_marketing_campaigns_external_source", table_name="marketing_campaigns")
    op.drop_column("marketing_campaigns", "advertising_connection_id")
    op.drop_column("marketing_campaigns", "external_id")
    op.drop_column("marketing_campaigns", "external_source")
