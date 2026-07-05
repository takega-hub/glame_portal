"""add look feed fields

Revision ID: 032_add_look_feed_fields
Revises: 031_add_sms_otp_limits_fields
Create Date: 2026-05-02 08:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "032_add_look_feed_fields"
down_revision = "031_add_sms_otp_limits_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("looks", sa.Column("caption", sa.Text(), nullable=True))
    op.add_column("looks", sa.Column("media_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("looks", sa.Column("product_layout", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("looks", sa.Column("source_provider", sa.String(length=64), nullable=True))
    op.add_column("looks", sa.Column("source_media_id", sa.String(length=128), nullable=True))
    op.add_column("looks", sa.Column("source_permalink", sa.String(length=500), nullable=True))
    op.add_column("looks", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("looks", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("looks", sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("looks", sa.Column("favorite_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_looks_source_media_id", "looks", ["source_media_id"])
    op.create_index("ix_looks_is_published", "looks", ["is_published"])
    op.create_index("ix_looks_published_at", "looks", ["published_at"])

    op.create_table(
        "look_reactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("look_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reaction_type", sa.String(length=50), nullable=False, server_default="like"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["look_id"], ["looks.id"]),
        sa.UniqueConstraint("user_id", "look_id", "reaction_type", name="uq_look_reactions_user_look_type"),
    )
    op.create_index("ix_look_reactions_user_id", "look_reactions", ["user_id"])
    op.create_index("ix_look_reactions_look_id", "look_reactions", ["look_id"])
    op.create_index("ix_look_reactions_look_type", "look_reactions", ["look_id", "reaction_type"])


def downgrade() -> None:
    op.drop_index("ix_look_reactions_look_type", table_name="look_reactions")
    op.drop_index("ix_look_reactions_look_id", table_name="look_reactions")
    op.drop_index("ix_look_reactions_user_id", table_name="look_reactions")
    op.drop_table("look_reactions")

    op.drop_index("ix_looks_published_at", table_name="looks")
    op.drop_index("ix_looks_is_published", table_name="looks")
    op.drop_index("ix_looks_source_media_id", table_name="looks")
    op.drop_column("looks", "favorite_count")
    op.drop_column("looks", "like_count")
    op.drop_column("looks", "published_at")
    op.drop_column("looks", "is_published")
    op.drop_column("looks", "source_permalink")
    op.drop_column("looks", "source_media_id")
    op.drop_column("looks", "source_provider")
    op.drop_column("looks", "product_layout")
    op.drop_column("looks", "media_items")
    op.drop_column("looks", "caption")
