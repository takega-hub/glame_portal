"""admin role access

Revision ID: 035_admin_role_access
Revises: 034_add_app_store_coordinates
Create Date: 2026-05-04 08:35:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


revision = "035_admin_role_access"
down_revision = "034_add_app_store_coordinates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_role_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_key", sa.String(length=50), nullable=False),
        sa.Column("role_label", sa.String(length=100), nullable=False),
        sa.Column("section_ids", sa.JSON(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_key"),
    )
    op.create_index("ix_admin_role_access_role_key", "admin_role_access", ["role_key"], unique=False)

    roles = [
        (
            "admin",
            "Админ",
            [
                "customer_stylist",
                "content_generator",
                "content_agent",
                "ai_marketer",
                "ai_marketer_tasks",
                "batch_messages",
                "knowledge_base",
                "products",
                "looks",
                "customers",
                "analytics",
                "product_analytics",
                "inventory_control",
                "inventory_tasks",
                "settings",
                "app_admin",
                "shipping_admin",
                "inventory_admin",
                "system_prompts",
                "roles_access",
            ],
        ),
        (
            "marketer",
            "Маркетолог",
            [
                "content_generator",
                "content_agent",
                "ai_marketer",
                "ai_marketer_tasks",
                "batch_messages",
                "customers",
                "analytics",
                "product_analytics",
                "app_admin",
            ],
        ),
        (
            "manager",
            "Управляющий",
            [
                "knowledge_base",
                "products",
                "looks",
                "customers",
                "analytics",
                "product_analytics",
                "inventory_control",
                "inventory_tasks",
                "app_admin",
                "shipping_admin",
                "inventory_admin",
            ],
        ),
        ("seller", "Продавец", ["customer_stylist", "products", "looks", "customers"]),
    ]

    admin_role_access = sa.table(
        "admin_role_access",
        sa.column("id", postgresql.UUID),
        sa.column("role_key", sa.String),
        sa.column("role_label", sa.String),
        sa.column("section_ids", sa.JSON),
        sa.column("is_system", sa.Boolean),
    )
    op.bulk_insert(
        admin_role_access,
        [
            {
                "id": uuid.uuid4(),
                "role_key": role_key,
                "role_label": label,
                "section_ids": section_ids,
                "is_system": True,
            }
            for role_key, label, section_ids in roles
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_role_access_role_key", table_name="admin_role_access")
    op.drop_table("admin_role_access")
