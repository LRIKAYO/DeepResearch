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

import contextvars
import json
import logging
from concurrent.futures import ThreadPoolExecutor
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
DEFAULT_MAX_TOOL_CALLS = 6
MAX_TOOL_CALLS_LIMIT = 30
MAX_PARALLEL_TOOL_WORKERS = 4


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
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
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
    lines.append(
        "Tool calls used: "
        f"{int(state.get('tool_calls_used', 0) or 0)} of {max_tool_calls}."
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
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
    system_prompt: str | None = None,
) -> dict:
    """Researcher node: decide the next search action, or stop.

    1. Read the run's research query (set by the planner).
    2. Bind the tool schema only while tool-round and tool-call budgets remain.
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
    tool_calls_used = int(state.get("tool_calls_used", 0) or 0)

    if tool_rounds < max_tool_rounds and tool_calls_used < max_tool_calls:
        model_with_tools = researcher_model.bind_tools(
            list(tool_registry.values()),
            parallel_tool_calls=True,
        )
    else:
        # Budget exhausted: no tool schema, so the model must answer from
        # existing evidence. This also guarantees no orphan tool_call can be
        # left unanswered when the loop ends.
        logger.info("tool budget exhausted; answering from current evidence")
        model_with_tools = researcher_model

    messages: list[Any] = []

    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))

    context = _research_context(
        state,
        max_tool_rounds=max_tool_rounds,
        max_tool_calls=max_tool_calls,
    )
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


def canonical_tool_query_key(tool_name: str, normalized_args: object) -> str | None:
    """Return a deterministic deduplication key for valid dict tool arguments."""

    if not isinstance(normalized_args, dict):
        return None

    canonical_args = dict(normalized_args)
    query = canonical_args.get("query")
    if isinstance(query, str) and query.strip():
        canonical_args["query"] = query.strip()

    try:
        serialized_args = json.dumps(
            canonical_args, sort_keys=True, ensure_ascii=False
        )
    except TypeError:
        return None

    return json.dumps([tool_name, serialized_args], ensure_ascii=False)


def _evidence_provenance_key(item: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return provenance identity for cross-round evidence deduplication."""

    source_type = item.get("source_type")
    provenance = item.get("provenance")
    if not isinstance(provenance, dict):
        return None

    if source_type == "user_upload":
        document_id = provenance.get("document_id")
        chunk_id = provenance.get("chunk_id")
        if document_id and chunk_id:
            return ("user_upload", str(document_id), str(chunk_id))
        return None

    if source_type == "temporary_research":
        url = provenance.get("url")
        content = item.get("content")
        if isinstance(url, str) and isinstance(content, str):
            return ("temporary_research", url, content)
        return None

    return None


def _invoke_single_tool_call(
    tool: Any,
    tool_call: dict[str, Any],
    normalized_args: object,
    *,
    recover_tool_errors: bool,
) -> tuple[list[dict[str, Any]], ToolMessage, bool]:
    """Invoke one tool call and return (validated_evidence, tool_message, succeeded)."""

    try:
        tool_result = tool.invoke(normalized_args)
    except Exception as exc:
        if not recover_tool_errors:
            raise
        logger.warning(
            "Tool %s failed during research run; degrading to error ToolMessage: %s",
            tool_call["name"],
            exc,
            exc_info=True,
        )
        return (
            [],
            ToolMessage(
                content=f"Tool error ({type(exc).__name__}): {exc}",
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
                status="error",
            ),
            False,
        )

    validated = validate_evidence_list(tool_result)
    return (
        validated,
        ToolMessage(
            content="Research evidence collected successfully.",
            tool_call_id=tool_call["id"],
            name=tool_call["name"],
        ),
        True,
    )


def execute_tool(
    state: AgentState,
    web_tool: Any,
    knowledge_client: KnowledgeClient,
    runtime: Runtime[AgentContext],
    *,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
    deduplicate_queries: bool = True,
    recover_tool_errors: bool = False,
) -> dict:
    """Execute pending tool calls, accumulating typed Evidence in deterministic order.

    Evidence accumulates across rounds; a later round must never erase what an
    earlier round found, while cross-round duplicate provenance is collapsed.
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

    tool_calls_used = int(state.get("tool_calls_used", 0) or 0)
    seen_queries = list(state.get("seen_tool_queries") or [])
    seen_query_set = set(seen_queries)
    batch_reserved_queries: set[str] = set()

    ordered_evidence: list[list[dict[str, Any]]] = [[] for _ in tool_calls]
    ordered_messages: list[ToolMessage | None] = [None] * len(tool_calls)
    executable: list[tuple[int, dict[str, Any], object, str | None]] = []

    for index, tool_call in enumerate(tool_calls):
        normalized_args = normalize_tool_args(tool_call["args"])
        query_key = (
            canonical_tool_query_key(tool_call["name"], normalized_args)
            if deduplicate_queries
            else None
        )

        if tool_calls_used >= max_tool_calls:
            ordered_messages[index] = ToolMessage(
                content="Skipped: tool-call budget exhausted.",
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            )
            continue

        if (
            deduplicate_queries
            and query_key is not None
            and (query_key in seen_query_set or query_key in batch_reserved_queries)
        ):
            ordered_messages[index] = ToolMessage(
                content="Duplicate tool query skipped; already executed in this run.",
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            )
            continue

        tool_calls_used += 1
        if query_key is not None:
            batch_reserved_queries.add(query_key)
        executable.append((index, tool_call, normalized_args, query_key))

    if len(executable) == 1:
        index, tool_call, normalized_args, query_key = executable[0]
        evidence_items, message, succeeded = _invoke_single_tool_call(
            tool_registry[tool_call["name"]],
            tool_call,
            normalized_args,
            recover_tool_errors=recover_tool_errors,
        )
        ordered_evidence[index] = evidence_items
        ordered_messages[index] = message
        if succeeded and query_key is not None and query_key not in seen_query_set:
            seen_queries.append(query_key)
            seen_query_set.add(query_key)
    elif len(executable) > 1:
        max_workers = min(MAX_PARALLEL_TOOL_WORKERS, len(executable))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for index, tool_call, normalized_args, query_key in executable:
                ctx = contextvars.copy_context()
                future = executor.submit(
                    ctx.run,
                    partial(
                        _invoke_single_tool_call,
                        tool_registry[tool_call["name"]],
                        tool_call,
                        normalized_args,
                        recover_tool_errors=recover_tool_errors,
                    ),
                )
                futures.append((index, query_key, future))

            for index, query_key, future in futures:
                evidence_items, message, succeeded = future.result()
                ordered_evidence[index] = evidence_items
                ordered_messages[index] = message
                if succeeded and query_key is not None and query_key not in seen_query_set:
                    seen_queries.append(query_key)
                    seen_query_set.add(query_key)

    existing_evidence = list(state.get("evidence") or [])
    seen_provenance: set[tuple[str, str, str]] = set()
    for item in existing_evidence:
        if isinstance(item, dict):
            prov_key = _evidence_provenance_key(item)
            if prov_key is not None:
                seen_provenance.add(prov_key)

    new_evidence: list[dict[str, Any]] = []
    dedup_against_prior = bool(existing_evidence)
    for batch_items in ordered_evidence:
        for item in batch_items:
            if dedup_against_prior:
                prov_key = _evidence_provenance_key(item)
                if prov_key is not None:
                    if prov_key in seen_provenance:
                        continue
                    seen_provenance.add(prov_key)
            new_evidence.append(item)

    tool_messages = [msg for msg in ordered_messages if msg is not None]

    return {
        "evidence": [*existing_evidence, *new_evidence],
        "tool_rounds": int(state.get("tool_rounds", 0) or 0) + 1,
        "tool_calls_used": tool_calls_used,
        "seen_tool_queries": seen_queries,
        "messages": tool_messages,
    }


def route_after_tools(
    state: AgentState,
    *,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
) -> Literal["researcher", "writer"]:
    """Continue the loop while tool-round and tool-call budgets remain."""

    tool_rounds = int(state.get("tool_rounds", 0) or 0)
    tool_calls_used = int(state.get("tool_calls_used", 0) or 0)
    if tool_rounds < max_tool_rounds and tool_calls_used < max_tool_calls:
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
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
    deduplicate_queries: bool = True,
    recover_tool_errors: bool = False,
    researcher_system_prompt: str | None = None,
):
    """Build the scoped, bounded research workflow."""

    if not isinstance(max_tool_rounds, int) or isinstance(max_tool_rounds, bool):
        raise ValueError("max_tool_rounds must be an integer")
    if not 1 <= max_tool_rounds <= MAX_TOOL_ROUNDS_LIMIT:
        raise ValueError(
            f"max_tool_rounds must be between 1 and {MAX_TOOL_ROUNDS_LIMIT}"
        )
    if not isinstance(max_tool_calls, int) or isinstance(max_tool_calls, bool):
        raise ValueError("max_tool_calls must be an integer")
    if not 1 <= max_tool_calls <= MAX_TOOL_CALLS_LIMIT:
        raise ValueError(
            f"max_tool_calls must be between 1 and {MAX_TOOL_CALLS_LIMIT}"
        )
    if not isinstance(context_radius, int) or isinstance(context_radius, bool):
        raise ValueError("context_radius must be an integer")
    if not 0 <= context_radius <= MAX_CONTEXT_RADIUS:
        raise ValueError(f"context_radius must be between 0 and {MAX_CONTEXT_RADIUS}")
    if not 0.0 <= weak_match_threshold <= 1.0:
        raise ValueError("weak_match_threshold must be between 0 and 1")
    if not isinstance(deduplicate_queries, bool):
        raise ValueError("deduplicate_queries must be a boolean")
    if not isinstance(recover_tool_errors, bool):
        raise ValueError("recover_tool_errors must be a boolean")

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
            max_tool_calls=max_tool_calls,
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
            max_tool_calls=max_tool_calls,
            context_radius=context_radius,
            weak_match_threshold=weak_match_threshold,
            deduplicate_queries=deduplicate_queries,
            recover_tool_errors=recover_tool_errors,
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
        partial(
            route_after_tools,
            max_tool_rounds=max_tool_rounds,
            max_tool_calls=max_tool_calls,
        ),
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
