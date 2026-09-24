"""Add customer requests and audit history.

Revision ID: 072_customer_requests
Revises: 071_crm_service_cases
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "072_customer_requests"
down_revision = "071_crm_service_cases"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("request_type", sa.String(48), nullable=False),
        sa.Column("physical_store", sa.String(64)), sa.Column("crm_store", sa.String(64)),
        sa.Column("assigned_consultant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(48), nullable=False), sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("product_name", sa.String(255)), sa.Column("sku", sa.String(128)), sa.Column("size", sa.String(32)), sa.Column("brand", sa.String(128)),
        sa.Column("original_comment", sa.Text()),
        sa.Column("structured_context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("next_action", sa.Text()), sa.Column("next_action_at", sa.DateTime(timezone=True)), sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    for name, columns in {
        "ix_customer_requests_open": ["status", "next_action_at"], "ix_customer_requests_client": ["client_id"],
        "ix_customer_requests_type": ["request_type"], "ix_customer_requests_store": ["crm_store"],
        "ix_customer_requests_assignee": ["assigned_consultant_id"], "ix_customer_requests_sku": ["sku"],
    }.items(): op.create_index(name, "customer_requests", columns)
    op.create_table(
        "customer_request_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customer_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False), sa.Column("old_status", sa.String(48)), sa.Column("new_status", sa.String(48)), sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_customer_request_audit_request", "customer_request_audit", ["request_id", "created_at"])
    op.execute("""UPDATE admin_role_access SET section_ids = (section_ids::jsonb || '[\"customer_requests\"]'::jsonb)::json WHERE role_key IN ('manager', 'seller') AND NOT (section_ids::jsonb ? 'customer_requests')""")


def downgrade():
    op.drop_table("customer_request_audit")
    op.drop_table("customer_requests")
