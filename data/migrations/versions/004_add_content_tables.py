"""Add content calendar tables (plans/items/publications)

Revision ID: 004_add_content_tables
Revises: 003_knowledge_documents
Create Date: 2026-01-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "004_add_content_tables"
down_revision = "003_knowledge_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("inputs", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_content_plans_status", "content_plans", ["status"])
    op.create_index("ix_content_plans_start_date", "content_plans", ["start_date"])
    op.create_index("ix_content_plans_end_date", "content_plans", ["end_date"])

    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False, server_default="post"),
        sa.Column("topic", sa.String(500), nullable=True),
        sa.Column("hook", sa.String(500), nullable=True),
        sa.Column("cta", sa.String(500), nullable=True),
        sa.Column("persona", sa.String(500), nullable=True),
        sa.Column("cjm_stage", sa.String(64), nullable=True),
        sa.Column("goal", sa.String(500), nullable=True),
        sa.Column("spec", postgresql.JSON, nullable=True),
        sa.Column("generated", postgresql.JSON, nullable=True),
        sa.Column("generated_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="planned"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publication_metadata", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["content_plans.id"], name="fk_content_items_plan_id"),
    )
    op.create_index("ix_content_items_plan_id", "content_items", ["plan_id"])
    op.create_index("ix_content_items_scheduled_at", "content_items", ["scheduled_at"])
    op.create_index("ix_content_items_status", "content_items", ["status"])
    op.create_index("ix_content_items_channel", "content_items", ["channel"])

    op.create_table(
        "content_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default="glame"),
        sa.Column("status", sa.String(50), nullable=False, server_default="created"),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("request_payload", postgresql.JSON, nullable=True),
        sa.Column("response_payload", postgresql.JSON, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["item_id"], ["content_items.id"], name="fk_content_publications_item_id"),
    )
    op.create_index("ix_content_publications_item_id", "content_publications", ["item_id"])
    op.create_index("ix_content_publications_status", "content_publications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_content_publications_status", table_name="content_publications")
    op.drop_index("ix_content_publications_item_id", table_name="content_publications")
    op.drop_table("content_publications")

    op.drop_index("ix_content_items_channel", table_name="content_items")
    op.drop_index("ix_content_items_status", table_name="content_items")
    op.drop_index("ix_content_items_scheduled_at", table_name="content_items")
    op.drop_index("ix_content_items_plan_id", table_name="content_items")
    op.drop_table("content_items")

    op.drop_index("ix_content_plans_end_date", table_name="content_plans")
    op.drop_index("ix_content_plans_start_date", table_name="content_plans")
    op.drop_index("ix_content_plans_status", table_name="content_plans")
    op.drop_table("content_plans")

