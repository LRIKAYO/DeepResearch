"""Minimal state contracts for the ResearchFlow agent graph."""

from typing import TypedDict

from langgraph.graph import MessagesState
from typing_extensions import NotRequired


class Evidence(TypedDict):
    """A provisional research item produced by a tool."""

    source: str
    content: str
    relevance_note: NotRequired[str]


class AgentInputState(MessagesState):
    """External conversation input for a research run."""


class AgentState(AgentInputState, total=False):
    """Internal state shared by the Researcher, Tool, and Writer."""

    research_query: str
    evidence: list[Evidence]
    report: str


class AgentOutputState(AgentInputState):
    """Stable graph output for programmatic and chat consumers."""

    report: str
