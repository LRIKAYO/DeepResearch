"""Minimal state contracts for the ResearchFlow agent graph."""

from uuid import UUID

from langgraph.graph import MessagesState
from pydantic import BaseModel, ConfigDict

from .citations import CitationPayload
from .evidence import EvidencePayload
from .knowledge_search import KnowledgeScope
from .verification import VerificationPayload


class AgentContext(BaseModel):
    """Immutable, run-scoped dependencies that never enter Graph State."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_scope: KnowledgeScope
    # Set by the Frontend when a run belongs to a Research Session; the run then
    # persists its report. Optional so a direct invocation without a session
    # (tests, CLI probes) still works.
    research_session_id: UUID | None = None


class AgentInputState(MessagesState):
    """External conversation input for a research run."""


class AgentState(AgentInputState, total=False):
    """Internal state shared by the Planner, Researcher, Tools, Writer, Verifier."""

    research_query: str
    sub_questions: list[str]
    tool_rounds: int
    evidence: list[EvidencePayload]
    report: str
    citations: list[CitationPayload]
    verification: list[VerificationPayload]


class AgentOutputState(AgentInputState):
    """Stable graph output for programmatic and chat consumers."""

    research_query: str
    sub_questions: list[str]
    # Always present because the Planner initialises it to 0; the Frontend shows
    # it as the research-progress counter.
    tool_rounds: int
    report: str
    citations: list[CitationPayload]
    verification: list[VerificationPayload]
