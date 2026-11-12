"""Research planning: turn one question into a small set of sub-questions.

The planner is the entry node of every research run. It owns two
responsibilities:

1. Normalize the latest user turn into a single ``research_query`` string.
2. Reset the per-run search slice of State (evidence and tool rounds) so that a
   second question on the same thread never inherits the previous run's sources.
   Resetting here - instead of inside the Researcher - keeps the Researcher free
   to accumulate evidence across tool rounds.

``report``, ``citations`` and ``verification`` are deliberately *not* reset
here. They are written only by a successful Writer/Verifier pass, so a run that
fails before writing leaves the previous successful triple intact - which is
what the Sources UI promises to show.
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .state import AgentState

logger = logging.getLogger(__name__)

MAX_SUB_QUESTIONS = 4
MAX_SUB_QUESTION_CHARS = 500


class ResearchPlan(BaseModel):
    """Structured planner output. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    # Upper bound is enforced by the validator (truncate) rather than by
    # Field(max_length=...), so an over-eager planner degrades instead of
    # failing the run.
    sub_questions: list[str] = Field(min_length=1)

    @field_validator("sub_questions")
    @classmethod
    def normalize(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()

        for item in value:
            text = item.strip()
            if not text or len(text) > MAX_SUB_QUESTION_CHARS:
                continue
            key = " ".join(text.split()).casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)

        if not cleaned:
            raise ValueError("research plan requires at least one sub-question")

        return cleaned[:MAX_SUB_QUESTIONS]


def normalize_research_query(content: object) -> str:
    """Normalize HumanMessage.content into a text-only research query.

    Supported: a string, or a list of text content blocks.
    Unsupported: any other type, or text that is empty after stripping.
    """

    if isinstance(content, str):
        query = content.strip()
        if not query:
            raise ValueError("research query cannot be empty")
        return query

    if isinstance(content, list):
        text_parts: list[str] = []

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue
            text = block.get("text")
            if not isinstance(text, str):
                continue
            text = text.strip()
            if text:
                text_parts.append(text)

        if not text_parts:
            raise ValueError("research query contains no valid text blocks")

        return "\n\n".join(text_parts)

    raise ValueError(
        "HumanMessage.content must be a string or a list of text blocks"
    )


def latest_research_query(state: AgentState) -> str:
    """Return the most recent user turn as the research question."""

    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return normalize_research_query(message.content)

    raise ValueError("research run requires at least one HumanMessage")


class PassthroughPlanner:
    """Fallback planner: one sub-question, identical to the research query.

    Used when no planner model is wired (tests, or a degraded deployment). It
    keeps the raw question verbatim so multi-paragraph input survives.
    """

    def invoke(self, payload: dict) -> dict:
        return {"sub_questions": [payload["research_query"]]}


def plan_research(state: AgentState, planner_impl: Any) -> dict:
    """Plan one research run and reset the per-run search slice of State."""

    research_query = latest_research_query(state)
    raw_plan = planner_impl.invoke({"research_query": research_query})
    sub_questions = coerce_sub_questions(raw_plan, research_query)

    return {
        "research_query": research_query,
        "sub_questions": sub_questions,
        "tool_rounds": 0,
        "evidence": [],
    }


def coerce_sub_questions(raw_plan: object, research_query: str) -> list[str]:
    """Accept a ResearchPlan, a dict, or degrade to the original question.

    A planner failure must never kill a research run: planning is an
    optimization, not a correctness requirement.
    """

    if isinstance(raw_plan, ResearchPlan):
        return raw_plan.sub_questions

    if isinstance(raw_plan, dict):
        try:
            return ResearchPlan.model_validate(raw_plan).sub_questions
        except ValidationError:
            logger.warning("planner returned an invalid plan; using the raw question")
            return [research_query]

    logger.warning("planner returned %s; using the raw question", type(raw_plan).__name__)
    return [research_query]
