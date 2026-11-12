import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from researchflow.knowledge.embeddings import embed_query
from researchflow.knowledge.retrieval import KnowledgeHit, search_knowledge

from .current_user import CurrentUserId
from .database import get_session
from .knowledge_dependencies import EmbeddingFactoryDependency
from .models import Document, DocumentChunk
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


# A wider window than this is not a context window any more; the measurement
# behind the default saturates at ±2 and adds nothing at ±3.
DEFAULT_CONTEXT_RADIUS = 2
MAX_CONTEXT_RADIUS = 3

router = APIRouter(prefix="/projects/{project_id}/knowledge", tags=["knowledge"])

RETRIEVAL_MODES = ("hybrid", "cosine")


def retrieval_mode() -> str:
    """Which ranking the search endpoint uses.

    ``hybrid`` is the default because it ranks the evaluation corpus better
    (Recall@3 0.744 -> 0.789, MRR 0.696 -> 0.720). ``cosine`` exists so the two
    can be compared on the same corpus without editing code.
    """

    raw = os.getenv("RESEARCHFLOW_RETRIEVAL_MODE", "hybrid").strip().lower()
    if raw not in RETRIEVAL_MODES:
        raise ValueError(
            f"RESEARCHFLOW_RETRIEVAL_MODE must be one of {', '.join(RETRIEVAL_MODES)}"
        )
    return raw


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
            query_text=payload.query,
            query_vector=query_vector,
            limit=payload.limit,
            use_lexical=retrieval_mode() == "hybrid",
        )
    except HTTPException:
        raise
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge search unavailable",
        ) from None


class ChunkContextResponse(BaseModel):
    """A matched chunk together with its immediate neighbours."""

    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    filename: str
    content: str
    start_index: int
    end_index: int


@router.get("/chunks/{chunk_id}/context", response_model=ChunkContextResponse)
def read_chunk_context(
    project_id: UUID,
    chunk_id: UUID,
    owner_user_id: CurrentUserId,
    radius: Annotated[int, Query(ge=0, le=MAX_CONTEXT_RADIUS)] = DEFAULT_CONTEXT_RADIUS,
    session: Session = Depends(get_session),
) -> ChunkContextResponse:
    """Return one chunk expanded by ``radius`` neighbours on each side.

    Retrieval returns chunks, but answers straddle chunk boundaries: on the
    evaluation corpus, the relevant passage sits within two chunks of a returned
    hit in 95.6% of answerable cases, against 88.9% for an exact hit. This
    endpoint is what lets the Agent hand the Writer a window instead of a sliver.

    **The matched chunk comes first**, then the chunks that follow it, then the
    ones that precede it. That order is deliberate: both the citation excerpt and
    the verifier read a prefix of the evidence (500 and 1200 characters), so a
    window in document order would push the matched passage out of the only part
    those readers ever see.

    Scope is enforced before the window is read: the chunk must belong to a
    Document of this Project, owned by this user.
    """

    require_project(session, project_id, owner_user_id)

    row = session.execute(
        select(
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
            Document.filename,
        )
        .join(Document, Document.document_id == DocumentChunk.document_id)
        .where(
            DocumentChunk.chunk_id == chunk_id,
            Document.project_id == project_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found"
        )

    document_id, centre, filename = row
    start_index = max(0, centre - radius)
    window = session.execute(
        select(DocumentChunk.chunk_index, DocumentChunk.content)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index >= start_index,
            DocumentChunk.chunk_index <= centre + radius,
        )
        .order_by(DocumentChunk.chunk_index.asc())
    ).all()

    matched = next(content for index, content in window if index == centre)
    following = [content for index, content in window if index > centre]
    preceding = [content for index, content in window if index < centre]

    return ChunkContextResponse(
        document_id=document_id,
        chunk_id=chunk_id,
        chunk_index=centre,
        filename=filename,
        content="\n\n".join([matched, *following, *preceding]),
        start_index=window[0][0],
        end_index=window[-1][0],
    )
