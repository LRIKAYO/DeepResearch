from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from researchflow.backend.models import Document, DocumentChunk
from researchflow.backend.projects import Project


@dataclass(frozen=True)
class KnowledgeHit:
    document_id: UUID
    chunk_id: UUID
    filename: str
    content: str
    score: float


def search_knowledge(
    session: Session,
    *,
    owner_user_id: UUID,
    project_id: UUID,
    query_vector: list[float],
    limit: int,
) -> list[KnowledgeHit]:
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    statement = (
        select(
            Document.document_id,
            DocumentChunk.chunk_id,
            Document.filename,
            DocumentChunk.content,
            distance.label("distance"),
        )
        .join(Document, Document.document_id == DocumentChunk.document_id)
        .join(Project, Project.project_id == Document.project_id)
        .where(
            Document.project_id == project_id,
            Project.owner_user_id == owner_user_id,
        )
        .order_by(distance.asc(), DocumentChunk.chunk_id.asc())
        .limit(limit)
    )
    return [
        KnowledgeHit(
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            filename=row.filename,
            content=row.content,
            score=1.0 - float(row.distance),
        )
        for row in session.execute(statement)
    ]
