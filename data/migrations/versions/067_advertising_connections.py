"""Create advertising connections registry."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "067_advertising_connections"
down_revision = "066_glame_token_bridge_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "advertising_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("account_login", sa.String(255)),
        sa.Column("client_login", sa.String(255)),
        sa.Column("organization_name", sa.String(255)),
        sa.Column("status", sa.String(64), nullable=False, server_default="draft"),
        sa.Column("auth_mode", sa.String(32), nullable=False, server_default="oauth"),
        sa.Column("secret_ref", sa.String(255)),
        sa.Column("permissions", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_status", sa.String(64)),
        sa.Column("last_sync_summary", postgresql.JSONB),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_advertising_connections_platform", "advertising_connections", ["platform"])
    op.create_index("ix_advertising_connections_status", "advertising_connections", ["status"])


def downgrade():
    op.drop_index("ix_advertising_connections_status", table_name="advertising_connections")
    op.drop_index("ix_advertising_connections_platform", table_name="advertising_connections")
    op.drop_table("advertising_connections")
