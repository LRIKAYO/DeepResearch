from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, StrictStr, field_validator
from sqlalchemy import CheckConstraint, DateTime, String, Uuid, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .database import get_session


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("char_length(name) > 0", name="projects_name_not_empty"),
    )

    project_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
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
def list_projects(session: Session = Depends(get_session)) -> list[Project]:
    statement = select(Project).order_by(
        Project.created_at.desc(),
        Project.project_id.desc(),
    )
    return list(session.scalars(statement))


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate, session: Session = Depends(get_session)
) -> Project:
    project = Project(project_id=uuid4(), name=payload.name)
    session.add(project)
    try:
        session.commit()
        session.refresh(project)
    except SQLAlchemyError:
        session.rollback()
        raise
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def read_project(project_id: UUID, session: Session = Depends(get_session)) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
