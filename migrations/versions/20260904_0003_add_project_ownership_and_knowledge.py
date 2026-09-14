"""add project ownership and knowledge tables

Revision ID: 20260904_0003
Revises: 20260831_0002
Create Date: 2026-09-04
"""

import os
from uuid import UUID

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260904_0003"
down_revision = "20260831_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "projects",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    connection = op.get_bind()
    project_count = connection.execute(
        sa.text("SELECT count(*) FROM projects")
    ).scalar_one()
    if project_count:
        legacy_owner = os.getenv("RESEARCHFLOW_LEGACY_OWNER_USER_ID")
        try:
            owner_user_id = UUID(legacy_owner) if legacy_owner else None
        except ValueError as exc:
            raise RuntimeError(
                "RESEARCHFLOW_LEGACY_OWNER_USER_ID must be a valid UUID"
            ) from exc
        if owner_user_id is None:
            raise RuntimeError(
                "RESEARCHFLOW_LEGACY_OWNER_USER_ID is required to migrate existing projects"
            )
        connection.execute(
            sa.text("UPDATE projects SET owner_user_id = :owner_user_id"),
            {"owner_user_id": owner_user_id},
        )
    op.alter_column("projects", "owner_user_id", nullable=False)
    op.create_index("ix_projects_owner_user_id", "projects", ["owner_user_id"])

    op.create_table(
        "documents",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(filename) > 0", name="documents_filename_not_empty"
        ),
        sa.CheckConstraint(
            "media_type = 'text/markdown'", name="documents_media_type_markdown"
        ),
        sa.CheckConstraint(
            "char_length(content_text) > 0", name="documents_content_text_not_empty"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])

    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=1024), nullable=False),
        sa.CheckConstraint(
            "chunk_index >= 0", name="document_chunks_index_non_negative"
        ),
        sa.CheckConstraint(
            "char_length(content) > 0", name="document_chunks_content_not_empty"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.document_id"]),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_index"
        ),
    )
    op.create_index(
        "ix_document_chunks_document_id", "document_chunks", ["document_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_project_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_projects_owner_user_id", table_name="projects")
    op.drop_column("projects", "owner_user_id")
    op.execute("DROP EXTENSION IF EXISTS vector")
