"""Persisted research Reports.

The Agent produces a report, its citation inventory and the verifier's verdicts
in Graph State, which lives in the LangGraph checkpoint. That checkpoint is
in-memory in the local development server, so a restart loses every report even
though the Product Backend still holds the Research Session row.

A Report row is therefore the durable copy: what the product can show after the
Agent Server forgets. It is deliberately append-only — a re-run adds a row rather
than overwriting one, so the history of a session stays readable and a failed run
can never destroy an earlier good report.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Uuid,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from .current_user import CurrentUserId
from .database import get_session
from .models import Base
from .research_sessions import ResearchSession, require_project

MAX_REPORT_CHARS = 200_000
MAX_VALIDATION_ITEMS = 200
LIST_LIMIT = 20


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("char_length(report) > 0", name="reports_report_not_empty"),
        CheckConstraint("tool_rounds >= 0", name="reports_tool_rounds_non_negative"),
        # Newest-first listing per session is the only read pattern; declared here
        # so autogenerate does not try to drop the index the migration created.
        Index("ix_reports_session_created", "research_session_id", "created_at"),
    )

    report_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    research_session_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("research_sessions.research_session_id"),
        nullable=False,
        index=True,
    )
    report: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    verification: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    tool_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: StrictStr
    citations: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_VALIDATION_ITEMS)
    verification: list[dict[str, Any]] = Field(
        default_factory=list, max_length=MAX_VALIDATION_ITEMS
    )
    tool_rounds: StrictInt = Field(default=0, ge=0, le=100)

    @field_validator("report")
    @classmethod
    def validate_report(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("report cannot be empty")
        if len(value) > MAX_REPORT_CHARS:
            raise ValueError(f"report cannot exceed {MAX_REPORT_CHARS} characters")
        return value


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: UUID
    research_session_id: UUID
    report: str
    citations: list[dict[str, Any]]
    verification: list[dict[str, Any]]
    tool_rounds: int
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


router = APIRouter(
    prefix="/projects/{project_id}/research-sessions/{research_session_id}/reports",
    tags=["reports"],
)


def require_research_session(
    db: Session, project_id: UUID, research_session_id: UUID, owner_user_id: UUID
) -> ResearchSession:
    require_project(db, project_id, owner_user_id)
    research_session = db.scalar(
        select(ResearchSession).where(
            ResearchSession.project_id == project_id,
            ResearchSession.research_session_id == research_session_id,
        )
    )
    if research_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research session not found",
        )
    return research_session


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    project_id: UUID,
    research_session_id: UUID,
    payload: ReportCreate,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> Report:
    """Append a Report to a session.

    Appending, never replacing: a re-run adds a row, so the previous report of the
    same session stays readable even if the new run is worse.
    """

    require_research_session(session, project_id, research_session_id, owner_user_id)

    report = Report(
        report_id=uuid4(),
        research_session_id=research_session_id,
        report=payload.report,
        citations=payload.citations,
        verification=payload.verification,
        tool_rounds=payload.tool_rounds,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


@router.get("", response_model=list[ReportResponse])
def list_reports(
    project_id: UUID,
    research_session_id: UUID,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> list[Report]:
    """The newest reports of one session, newest first."""

    require_research_session(session, project_id, research_session_id, owner_user_id)
    statement = (
        select(Report)
        .where(Report.research_session_id == research_session_id)
        .order_by(Report.created_at.desc(), Report.report_id.desc())
        .limit(LIST_LIMIT)
    )
    return list(session.scalars(statement))


@router.get("/{report_id}", response_model=ReportResponse)
def read_report(
    project_id: UUID,
    research_session_id: UUID,
    report_id: UUID,
    owner_user_id: CurrentUserId,
    session: Session = Depends(get_session),
) -> Report:
    require_research_session(session, project_id, research_session_id, owner_user_id)
    report = session.scalar(
        select(Report).where(
            Report.report_id == report_id,
            Report.research_session_id == research_session_id,
        )
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    return report
