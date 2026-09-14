import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import DateTime, ForeignKey, Text, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .agent_server import AgentServerClient, get_agent_server
from .current_user import CurrentUserId
from .database import get_session
from .models import Base
from .projects import Project


logger = logging.getLogger(__name__)


class ResearchSession(Base):
    __tablename__ = "research_sessions"

    research_session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class ResearchSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    research_session_id: UUID
    project_id: UUID
    thread_id: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


def require_project(db: Session, project_id: UUID, owner_user_id: UUID) -> None:
    project = db.scalar(
        select(Project).where(
            Project.project_id == project_id,
            Project.owner_user_id == owner_user_id,
        )
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )


def create_research_session(
    *,
    db: Session,
    agent_server: AgentServerClient,
    project_id: UUID,
    owner_user_id: UUID,
) -> ResearchSession:
    require_project(db, project_id, owner_user_id)
    db.rollback()

    research_session_id = uuid4()
    try:
        thread_id = agent_server.create_thread(
            project_id=str(project_id),
            research_session_id=str(research_session_id),
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service unavailable",
        ) from None

    research_session = ResearchSession(
        research_session_id=research_session_id,
        project_id=project_id,
        thread_id=thread_id,
    )
    try:
        db.add(research_session)
        db.commit()
    except Exception:
        db.rollback()
        try:
            agent_server.delete_thread(thread_id)
        except Exception:
            logger.exception(
                "Failed to delete orphan LangGraph thread",
                extra={
                    "thread_id": thread_id,
                    "project_id": str(project_id),
                    "research_session_id": str(research_session_id),
                },
            )
        raise
    return research_session


router = APIRouter(
    prefix="/projects/{project_id}/research-sessions",
    tags=["research-sessions"],
)


@router.post(
    "",
    response_model=ResearchSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_session_route(
    project_id: UUID,
    owner_user_id: CurrentUserId,
    db: Session = Depends(get_session),
    agent_server: AgentServerClient = Depends(get_agent_server),
) -> ResearchSession:
    return create_research_session(
        db=db,
        agent_server=agent_server,
        project_id=project_id,
        owner_user_id=owner_user_id,
    )


@router.get("", response_model=list[ResearchSessionResponse])
def list_research_sessions(
    project_id: UUID,
    owner_user_id: CurrentUserId,
    db: Session = Depends(get_session),
) -> list[ResearchSession]:
    require_project(db, project_id, owner_user_id)
    statement = (
        select(ResearchSession)
        .where(ResearchSession.project_id == project_id)
        .order_by(
            ResearchSession.created_at.desc(),
            ResearchSession.research_session_id.desc(),
        )
    )
    return list(db.scalars(statement))


@router.get(
    "/{research_session_id}",
    response_model=ResearchSessionResponse,
)
def read_research_session(
    project_id: UUID,
    research_session_id: UUID,
    owner_user_id: CurrentUserId,
    db: Session = Depends(get_session),
) -> ResearchSession:
    require_project(db, project_id, owner_user_id)
    statement = select(ResearchSession).where(
        ResearchSession.project_id == project_id,
        ResearchSession.research_session_id == research_session_id,
    )
    research_session = db.scalar(statement)
    if research_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research session not found",
        )
    return research_session
