from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "015_soft_delete_agent_tasks"
down_revision = "add_external_analytics"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_interaction_tasks",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "agent_interaction_tasks",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_interaction_tasks",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_interaction_tasks",
        sa.Column("deleted_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_agent_task_deleted",
        "agent_interaction_tasks",
        ["is_deleted"],
        unique=False,
    )
    # Drop server default to keep model control
    op.alter_column(
        "agent_interaction_tasks",
        "is_deleted",
        server_default=None,
    )


def downgrade():
    op.drop_index("idx_agent_task_deleted", table_name="agent_interaction_tasks")
    op.drop_column("agent_interaction_tasks", "deleted_reason")
    op.drop_column("agent_interaction_tasks", "deleted_by")
    op.drop_column("agent_interaction_tasks", "deleted_at")
    op.drop_column("agent_interaction_tasks", "is_deleted")

