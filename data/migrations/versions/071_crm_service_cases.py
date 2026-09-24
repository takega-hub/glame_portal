"""Create CRM service cases for commercial-touch blocking."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "071_crm_service_cases"
down_revision = "070_product_stock_arrival_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_service_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("case_type", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_service_cases_customer", "crm_service_cases", ["customer_id"])
    op.create_index("ix_crm_service_cases_status", "crm_service_cases", ["status"])
    op.create_index("ix_crm_service_cases_type", "crm_service_cases", ["case_type"])
    op.create_index("ix_crm_service_cases_customer_status", "crm_service_cases", ["customer_id", "status"])


def downgrade():
    op.drop_index("ix_crm_service_cases_customer_status", table_name="crm_service_cases")
    op.drop_index("ix_crm_service_cases_type", table_name="crm_service_cases")
    op.drop_index("ix_crm_service_cases_status", table_name="crm_service_cases")
    op.drop_index("ix_crm_service_cases_customer", table_name="crm_service_cases")
    op.drop_table("crm_service_cases")
