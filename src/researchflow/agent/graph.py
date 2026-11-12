"""Research graph: plan -> bounded tool loop -> report -> citation verification.

    START
      |
      v
    planner            decompose the question, reset the per-run state slice
      |
      v
    researcher <-----------------+
      |                          |
      | tool_calls               | tool_rounds < max_tool_rounds
      v                          |
    execute_tool ----------------+
      |
      | no tool_calls, or budget exhausted
      v
    writer             report + [cN] citation markers
      |
      v
    verifier           does each citation actually support its claim?
      |
      v
     END
"""

import json
import logging
from functools import partial
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from .citations import map_evidence_to_citations
from .evidence import render_evidence_block, validate_evidence_list
from .knowledge_search import (
    DEFAULT_ABSTAIN_THRESHOLD,
    MAX_CONTEXT_RADIUS,
    KnowledgeClient,
    build_knowledge_search_tool,
)
from .persistence import ReportPersister
from .plan import PassthroughPlanner, normalize_research_query, plan_research
from .state import AgentContext, AgentInputState, AgentOutputState, AgentState
from .verification import verify_citations

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ROUNDS = 3
MAX_TOOL_ROUNDS_LIMIT = 10


def build_tool_registry(
    *,
    context: AgentContext | None,
    web_tool: Any,
    knowledge_client: KnowledgeClient,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
) -> dict[str, Any]:
    """Build the fixed two-Tool registry for one scoped graph run."""

    if context is None:
        raise ValueError("knowledge_scope runtime context is required")
    context = AgentContext.model_validate(context)
    if web_tool.name != "web_search":
        raise ValueError("web Tool must be named 'web_search'")

    knowledge_tool = build_knowledge_search_tool(
        scope=context.knowledge_scope,
        client=knowledge_client,
        context_radius=context_radius,
        weak_match_threshold=weak_match_threshold,
    )
    return {
        web_tool.name: web_tool,
        knowledge_tool.name: knowledge_tool,
    }



def _research_context(
    state: AgentState,
    *,
    max_tool_rounds: int,
) -> str | None:
    """Describe the plan and the evidence gathered so far.

    Without this the model cannot tell what it has already found, and the loop
    degenerates into calling tools blindly until the budget runs out.
    """

    sub_questions = state.get("sub_questions") or []
    evidence = state.get("evidence") or []

    if not sub_questions and not evidence:
        return None

    lines: list[str] = []

    if sub_questions:
        lines.append("Research sub-questions:")
        lines.extend(
            f"{index}. {question}"
            for index, question in enumerate(sub_questions, start=1)
        )
        lines.append("")

    if evidence:
        lines.append("Evidence collected so far:")
        lines.append(render_evidence_block(evidence))
        lines.append("")

    lines.append(
        "Tool rounds used: "
        f"{int(state.get('tool_rounds', 0) or 0)} of {max_tool_rounds}."
    )

    return "\n".join(lines)


def researcher(
    state: AgentState,
    researcher_model: Any,
    web_tool: Any,
    knowledge_client: KnowledgeClient,
    runtime: Runtime[AgentContext],
    *,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
    system_prompt: str | None = None,
) -> dict:
    """Researcher node: decide the next search action, or stop.

    1. Read the run's research query (set by the planner).
    2. Bind the tool schema only while tool-round budget remains.
    3. Invoke the model once with the plan and the evidence gathered so far.
    4. Append the model response; evidence accumulates elsewhere.
    """

    research_query = state.get("research_query") or normalize_research_query(
        _latest_human_content(state)
    )

    tool_registry = build_tool_registry(
        context=runtime.context,
        web_tool=web_tool,
        knowledge_client=knowledge_client,
        context_radius=context_radius,
        weak_match_threshold=weak_match_threshold,
    )

    tool_rounds = int(state.get("tool_rounds", 0) or 0)

    if tool_rounds < max_tool_rounds:
        model_with_tools = researcher_model.bind_tools(
            list(tool_registry.values()),
            parallel_tool_calls=True,
        )
    else:
        # Budget exhausted: no tool schema, so the model must answer from
        # existing evidence. This also guarantees no orphan tool_call can be
        # left unanswered when the loop ends.
        logger.info("tool-round budget exhausted; answering from current evidence")
        model_with_tools = researcher_model

    messages: list[Any] = []

    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    context = _research_context(state, max_tool_rounds=max_tool_rounds)
    if context:
        messages.append(SystemMessage(content=context))

    messages.extend(state["messages"])

    response = model_with_tools.invoke(messages)

    return {
        "research_query": research_query,
        "messages": [response],
    }


def route_after_researcher(state: AgentState) -> Literal["execute_tool", "writer"]:
    """With tool calls, execute them; without, the model has stopped searching."""

    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "execute_tool"

    return "writer"


def normalize_tool_args(args: object) -> object:
    """Unwrap the tool-argument shapes providers actually emit.

    Some OpenAI-compatible providers return the arguments as a JSON string, or
    wrap them as ``{"arguments": "{...}"}``. Passing that straight to a LangChain
    tool fails schema validation and kills the whole run, so the two known
    wrappers are unwrapped here. Anything else is left untouched: silently
    repairing arbitrary shapes would hide a real model failure.
    """

    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except ValueError:
            return args
        return parsed if isinstance(parsed, dict) else args

    if (
        isinstance(args, dict)
        and set(args) == {"arguments"}
        and isinstance(args["arguments"], str)
    ):
        try:
            parsed = json.loads(args["arguments"])
        except ValueError:
            return args
        if isinstance(parsed, dict):
            return parsed

    return args


def execute_tool(
    state: AgentState,
    web_tool: Any,
    knowledge_client: KnowledgeClient,
    runtime: Runtime[AgentContext],
    *,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
) -> dict:
    """Execute every pending tool call, accumulating typed Evidence.

    Evidence accumulates across rounds; a later round must never erase what an
    earlier round found.
    """

    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage):
        raise ValueError("execute_tool requires the last message to be an AIMessage")

    tool_calls = last_message.tool_calls

    if len(tool_calls) == 0:
        raise ValueError(
            "execute_tool requires at least one tool call, but none were found"
        )

    tool_registry = build_tool_registry(
        context=runtime.context,
        web_tool=web_tool,
        knowledge_client=knowledge_client,
        context_radius=context_radius,
        weak_match_threshold=weak_match_threshold,
    )

    # Validate every name before invoking anything: an unknown tool must not
    # leave the run with half of its searches already sent to a provider.
    for tool_call in tool_calls:
        if tool_call["name"] not in tool_registry:
            raise ValueError(f"Unknown tool: {tool_call['name']}")

    new_evidence: list[dict] = []
    tool_messages: list[ToolMessage] = []

    for tool_call in tool_calls:
        tool = tool_registry[tool_call["name"]]
        tool_result = tool.invoke(normalize_tool_args(tool_call["args"]))
        new_evidence.extend(validate_evidence_list(tool_result))
        tool_messages.append(
            ToolMessage(
                content="Research evidence collected successfully.",
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            )
        )

    return {
        "evidence": [*(state.get("evidence") or []), *new_evidence],
        "tool_rounds": int(state.get("tool_rounds", 0) or 0) + 1,
        "messages": tool_messages,
    }


def route_after_tools(
    state: AgentState,
    *,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
) -> Literal["researcher", "writer"]:
    """Continue the loop while tool-round budget remains."""

    if int(state.get("tool_rounds", 0) or 0) < max_tool_rounds:
        return "researcher"

    return "writer"


def writer(
    state: AgentState,
    writer_impl: Any,
) -> dict:
    """Generate the report and the citation inventory from validated Evidence.

    Writer input boundary: research_query, sub_questions, evidence.
    ToolMessage content is execution trace only and is never research material.
    """

    research_query = state.get("research_query")

    if research_query is None:
        raise ValueError("writer requires 'research_query' in state")

    evidence = state.get("evidence")
    if evidence is None:
        evidence = []

    citations = map_evidence_to_citations(evidence)

    report = writer_impl.invoke(
        {
            "research_query": research_query,
            "sub_questions": list(state.get("sub_questions") or []),
            "evidence": evidence,
        }
    )

    if not isinstance(report, str):
        raise ValueError("writer_impl must return a string report")

    return {
        "report": report,
        "citations": citations,
        "messages": [AIMessage(content=report)],
    }


def persist(
    state: AgentState,
    persister: ReportPersister | None,
    runtime: Runtime[AgentContext],
) -> dict:
    """Write the finished run to the Product Backend, best effort.

    The report already exists, so a persistence failure is logged rather than
    raised: losing a history row is cheaper than losing the answer.
    """

    context = runtime.context
    session_id = getattr(context, "research_session_id", None)
    report = state.get("report")

    if persister is None or session_id is None or not isinstance(report, str):
        return {}

    try:
        report_id = persister.save(
            user_id=context.knowledge_scope.user_id,
            project_id=context.knowledge_scope.project_id,
            research_session_id=session_id,
            report=report,
            citations=list(state.get("citations") or []),
            verification=list(state.get("verification") or []),
            tool_rounds=int(state.get("tool_rounds", 0) or 0),
        )
    except Exception:
        logger.warning("report persistence failed; the run result is unchanged", exc_info=True)
        return {}

    if report_id is None:
        logger.warning("backend rejected the report write; the run result is unchanged")
        return {}

    logger.info("persisted report %s for session %s", report_id, session_id)
    return {}


def verifier(state: AgentState, verifier_impl: Any) -> dict:
    """Check whether each citation actually supports the sentence citing it."""

    if verifier_impl is None:
        return {"verification": []}

    return verify_citations(state, verifier_impl)


def build_graph(
    researcher_model: Any,
    web_tool: Any,
    knowledge_client: KnowledgeClient,
    writer_impl: Any,
    planner_impl: Any = None,
    verifier_impl: Any = None,
    persist_impl: ReportPersister | None = None,
    *,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
    researcher_system_prompt: str | None = None,
):
    """Build the scoped, bounded research workflow."""

    if not isinstance(max_tool_rounds, int) or isinstance(max_tool_rounds, bool):
        raise ValueError("max_tool_rounds must be an integer")
    if not 1 <= max_tool_rounds <= MAX_TOOL_ROUNDS_LIMIT:
        raise ValueError(
            f"max_tool_rounds must be between 1 and {MAX_TOOL_ROUNDS_LIMIT}"
        )
    if not isinstance(context_radius, int) or isinstance(context_radius, bool):
        raise ValueError("context_radius must be an integer")
    if not 0 <= context_radius <= MAX_CONTEXT_RADIUS:
        raise ValueError(f"context_radius must be between 0 and {MAX_CONTEXT_RADIUS}")
    if not 0.0 <= weak_match_threshold <= 1.0:
        raise ValueError("weak_match_threshold must be between 0 and 1")

    planner = planner_impl if planner_impl is not None else PassthroughPlanner()

    builder = StateGraph(
        AgentState,
        context_schema=AgentContext,
        input_schema=AgentInputState,
        output_schema=AgentOutputState,
    )

    builder.add_node("planner", partial(plan_research, planner_impl=planner))

    builder.add_node(
        "researcher",
        partial(
            researcher,
            researcher_model=researcher_model,
            web_tool=web_tool,
            knowledge_client=knowledge_client,
            max_tool_rounds=max_tool_rounds,
            context_radius=context_radius,
            weak_match_threshold=weak_match_threshold,
            system_prompt=researcher_system_prompt,
        ),
    )

    builder.add_node(
        "execute_tool",
        partial(
            execute_tool,
            web_tool=web_tool,
            knowledge_client=knowledge_client,
            context_radius=context_radius,
            weak_match_threshold=weak_match_threshold,
        ),
    )

    builder.add_node("writer", partial(writer, writer_impl=writer_impl))

    builder.add_node("verifier", partial(verifier, verifier_impl=verifier_impl))

    builder.add_node("persist", partial(persist, persister=persist_impl))

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "researcher")

    builder.add_conditional_edges(
        "researcher",
        route_after_researcher,
        {
            "execute_tool": "execute_tool",
            "writer": "writer",
        },
    )

    builder.add_conditional_edges(
        "execute_tool",
        partial(route_after_tools, max_tool_rounds=max_tool_rounds),
        {
            "researcher": "researcher",
            "writer": "writer",
        },
    )

    builder.add_edge("writer", "verifier")
    builder.add_edge("verifier", "persist")
    builder.add_edge("persist", END)

    return builder.compile()


def _latest_human_content(state: AgentState) -> object:
    """Fallback for direct node calls that bypassed the planner."""

    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content

    raise ValueError("researcher requires at least one HumanMessage")
