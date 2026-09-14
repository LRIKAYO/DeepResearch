from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from researchflow.knowledge.chunking import chunk_markdown
from researchflow.knowledge.embeddings import embed_documents

from .current_user import CurrentUserId
from .database import get_session
from .knowledge_dependencies import EmbeddingFactoryDependency
from .models import Document, DocumentChunk
from .research_sessions import require_project


MAX_MARKDOWN_BYTES = 1_048_576


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    project_id: UUID
    filename: str
    media_type: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    project_id: UUID,
    owner_user_id: CurrentUserId,
    request: Request,
    file: Annotated[UploadFile, File()],
    embedding_factory: EmbeddingFactoryDependency,
    session: Session = Depends(get_session),
) -> Document:
    require_project(session, project_id, owner_user_id)
    _reject_undeclared_form_parts(await request.form())
    filename = _validate_filename(file.filename)
    if file.content_type != "text/markdown":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only text/markdown is supported",
        )
    raw_content = await file.read(MAX_MARKDOWN_BYTES + 1)
    if len(raw_content) > MAX_MARKDOWN_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Markdown document exceeds the 1048576-byte limit",
        )
    try:
        content_text = raw_content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Markdown document must be UTF-8",
        ) from None
    if not content_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Markdown document cannot be empty",
        )

    try:
        chunks = chunk_markdown(content_text)
        if not chunks:
            raise ValueError("Chunking produced no content")
        session.rollback()
        vectors = embed_documents(
            embedding_factory(),
            [chunk.content for chunk in chunks],
        )
        document = Document(
            document_id=uuid4(),
            project_id=project_id,
            filename=filename,
            media_type="text/markdown",
            content_text=content_text,
        )
        document_chunks = [
            DocumentChunk(
                chunk_id=uuid4(),
                document_id=document.document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        session.add_all([document, *document_chunks])
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge indexing unavailable",
        ) from None
    return document


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    project_id: UUID,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> list[Document]:
    require_project(session, project_id, owner_user_id)
    statement = (
        select(Document)
        .where(Document.project_id == project_id)
        .order_by(Document.created_at.desc(), Document.document_id.desc())
    )
    return list(session.scalars(statement))


@router.get("/{document_id}", response_model=DocumentResponse)
def read_document(
    project_id: UUID,
    document_id: UUID,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> Document:
    require_project(session, project_id, owner_user_id)
    document = session.scalar(
        select(Document).where(
            Document.project_id == project_id,
            Document.document_id == document_id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


def _validate_filename(filename: str | None) -> str:
    normalized = filename.strip() if filename else ""
    if (
        not normalized
        or len(normalized) > 255
        or not normalized.lower().endswith(".md")
        or any(character in normalized for character in ("/", "\\", "\0"))
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid Markdown filename",
        )
    return normalized


def _reject_undeclared_form_parts(form) -> None:
    if set(form.keys()) != {"file"} or len(form.getlist("file")) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[
                {
                    "type": "extra_forbidden",
                    "loc": ["body"],
                    "msg": "Only one file part is allowed",
                    "input": None,
                }
            ],
        )
