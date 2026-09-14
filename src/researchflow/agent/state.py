"""Minimal state contracts for the ResearchFlow agent graph."""

from langgraph.graph import MessagesState
from pydantic import BaseModel, ConfigDict

from .citations import CitationPayload
from .evidence import EvidencePayload
from .knowledge_search import KnowledgeScope


class AgentContext(BaseModel):
    """Immutable, run-scoped dependencies that never enter Graph State."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_scope: KnowledgeScope


class AgentInputState(MessagesState):
    """External conversation input for a research run."""


class AgentState(AgentInputState, total=False):
    """Internal state shared by the Researcher, Tool, and Writer."""

    research_query: str
    evidence: list[EvidencePayload]
    report: str
    citations: list[CitationPayload]


class AgentOutputState(AgentInputState):
    """Stable graph output for programmatic and chat consumers."""

    report: str
    citations: list[CitationPayload]
