"""create research sessions

Revision ID: 20260831_0002
Revises: 20260830_0001
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_0002"
down_revision = "20260830_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_sessions",
        sa.Column("research_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("research_session_id"),
        sa.UniqueConstraint("thread_id"),
    )
    op.create_index(
        "ix_research_sessions_project_id",
        "research_sessions",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_sessions_project_id", table_name="research_sessions")
    op.drop_table("research_sessions")
