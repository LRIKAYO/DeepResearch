from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy.orm import Session

from researchflow.knowledge.embeddings import embed_query
from researchflow.knowledge.retrieval import KnowledgeHit, search_knowledge

from .current_user import CurrentUserId
from .database import get_session
from .knowledge_dependencies import EmbeddingFactoryDependency
from .research_sessions import require_project


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: StrictStr
    limit: StrictInt = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        query = value.strip()
        if not query or len(query) > 2000:
            raise ValueError("query must contain 1 to 2000 non-whitespace characters")
        return query


class KnowledgeHitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    chunk_id: UUID
    filename: str
    content: str
    score: float


router = APIRouter(prefix="/projects/{project_id}/knowledge", tags=["knowledge"])


@router.post("/search", response_model=list[KnowledgeHitResponse])
def search_project_knowledge(
    project_id: UUID,
    payload: KnowledgeSearchRequest,
    owner_user_id: CurrentUserId,
    embedding_factory: EmbeddingFactoryDependency,
    session: Session = Depends(get_session),
) -> list[KnowledgeHit]:
    try:
        require_project(session, project_id, owner_user_id)
        session.rollback()
        query_vector = embed_query(embedding_factory(), payload.query)
        return search_knowledge(
            session,
            owner_user_id=owner_user_id,
            project_id=project_id,
            query_vector=query_vector,
            limit=payload.limit,
        )
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge search unavailable",
        ) from None
