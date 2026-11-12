"""add reports

Revision ID: 20261111_0004
Revises: 20260904_0003
Create Date: 2026-11-11
"""

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa


revision = "20261111_0004"
down_revision = "20260904_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "verification",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "tool_rounds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("char_length(report) > 0", name="reports_report_not_empty"),
        sa.CheckConstraint("tool_rounds >= 0", name="reports_tool_rounds_non_negative"),
        sa.ForeignKeyConstraint(
            ["research_session_id"], ["research_sessions.research_session_id"]
        ),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_index("ix_reports_research_session_id", "reports", ["research_session_id"])
    # Newest-first listing per session is the only read pattern.
    op.create_index(
        "ix_reports_session_created",
        "reports",
        ["research_session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reports_session_created", table_name="reports")
    op.drop_index("ix_reports_research_session_id", table_name="reports")
    op.drop_table("reports")
