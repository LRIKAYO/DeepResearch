from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, StrictStr, field_validator
from sqlalchemy import CheckConstraint, DateTime, String, Uuid, delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .current_user import CurrentUserId
from .database import get_session
from .models import Base, Document, DocumentChunk


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("char_length(name) > 0", name="projects_name_not_empty"),
    )

    project_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StrictStr

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        name = value.strip()
        if not name or len(name) > 120:
            raise ValueError("name must contain 1 to 120 non-whitespace characters")
        return name


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    name: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> list[Project]:
    statement = (
        select(Project)
        .where(Project.owner_user_id == owner_user_id)
        .order_by(
            Project.created_at.desc(),
            Project.project_id.desc(),
        )
    )
    return list(session.scalars(statement))


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> Project:
    project = Project(
        project_id=uuid4(),
        owner_user_id=owner_user_id,
        name=payload.name,
    )
    session.add(project)
    try:
        session.commit()
        session.refresh(project)
    except SQLAlchemyError:
        session.rollback()
        raise
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def read_project(
    project_id: UUID,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> Project:
    project = session.scalar(
        select(Project).where(
            Project.project_id == project_id,
            Project.owner_user_id == owner_user_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> None:
    """Delete a Project and everything scoped to it.

    Row order is explicit because the foreign keys have no ON DELETE CASCADE:
    chunks reference documents, documents and research sessions reference the
    project. Deleting the project last keeps the transaction all-or-nothing.
    """

    # Imported here: research_sessions imports this module, so a module-level
    # import would be circular.
    from .reports import Report
    from .research_sessions import ResearchSession

    project = session.scalar(
        select(Project).where(
            Project.project_id == project_id,
            Project.owner_user_id == owner_user_id,
        )
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )

    session_ids = select(ResearchSession.research_session_id).where(
        ResearchSession.project_id == project_id
    )
    session.execute(
        delete(Report).where(Report.research_session_id.in_(session_ids))
    )
    document_ids = select(Document.document_id).where(Document.project_id == project_id)
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids))
    )
    session.execute(delete(Document).where(Document.project_id == project_id))
    session.execute(delete(ResearchSession).where(ResearchSession.project_id == project_id))
    session.execute(delete(Project).where(Project.project_id == project_id))
    session.commit()
