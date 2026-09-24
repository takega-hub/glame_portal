"""Create product stock arrival events for CRM new-arrival clienteling."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "070_product_stock_arrival_events"
down_revision = "069_advertising_daily_metrics"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_stock_arrival_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.String(length=255), nullable=False),
        sa.Column("previous_available_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("available_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("delta_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("event_type", sa.String(length=64), nullable=False, server_default="RESTOCK"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="onec_stock_sync"),
        sa.Column("source_sync_id", sa.String(length=128), nullable=False),
        sa.Column("source_idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_idempotency_key", name="uq_product_stock_arrival_events_idempotency"),
    )
    op.create_index("ix_stock_arrival_events_product", "product_stock_arrival_events", ["product_id"])
    op.create_index("ix_stock_arrival_events_store_received", "product_stock_arrival_events", ["store_id", "received_at"])
    op.create_index("ix_stock_arrival_events_processed_received", "product_stock_arrival_events", ["processed_at", "received_at"])
    op.create_index("ix_stock_arrival_events_event_type", "product_stock_arrival_events", ["event_type"])


def downgrade():
    op.drop_index("ix_stock_arrival_events_event_type", table_name="product_stock_arrival_events")
    op.drop_index("ix_stock_arrival_events_processed_received", table_name="product_stock_arrival_events")
    op.drop_index("ix_stock_arrival_events_store_received", table_name="product_stock_arrival_events")
    op.drop_index("ix_stock_arrival_events_product", table_name="product_stock_arrival_events")
    op.drop_table("product_stock_arrival_events")
