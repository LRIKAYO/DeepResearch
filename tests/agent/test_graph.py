import pytest

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime
from pydantic import ValidationError

from researchflow.agent.evidence import (
    TemporaryResearchEvidence,
    TemporaryWebProvenance,
    validate_evidence_list,
)
from researchflow.agent.graph import build_graph, researcher
import researchflow.agent.graph as graph_module
from researchflow.agent.knowledge_search import (
    KnowledgeHit,
    KnowledgeScope,
    KnowledgeSearchError,
)
from researchflow.agent.state import AgentContext


TEST_CONTEXT = AgentContext(
    knowledge_scope=KnowledgeScope(
        user_id="11111111-1111-1111-1111-111111111111",
        project_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
)


def temporary_evidence(
    source: str = "https://example.com",
    content: str = "result",
    relevance_note: str | None = None,
) -> TemporaryResearchEvidence:
    return TemporaryResearchEvidence(
        source_label=source,
        content=content,
        relevance_note=relevance_note,
        provenance=TemporaryWebProvenance(url=source),
    )


class FakeResearcherModel:
    def __init__(self, response: AIMessage, events: list[str]):
        self.response = response
        self.events = events
        self.bound_tools = None
        self.received_messages = None

    def bind_tools(self, tools, **kwargs):
        self.bound_tools = tools
        self.bound_tool_options = kwargs
        return self

    def invoke(self, messages):
        self.events.append("researcher")
        self.received_messages = messages
        return self.response


class FakeTool:
    def __init__(self, result: object, events: list[str], name: str="web_search"):
        self.result = result
        self.events = events
        self.name = name
        self.call_count = 0
        self.received_args = []

    def invoke(self, args):
        self.events.append("execute_tool")
        self.call_count += 1
        self.received_args.append(args)
        return self.result


class FakeKnowledgeClient:
    def __init__(self, result=None, events=None, error=None):
        self.result = result or []
        self.events = events
        self.error = error
        self.calls = []

    def search(self, *, scope, query, limit):
        if self.events is not None:
            self.events.append("knowledge_search")
        self.calls.append((scope, query, limit))
        if self.error is not None:
            raise self.error
        return self.result


def build_test_graph(
    researcher_model,
    web_tool,
    writer_impl,
    knowledge_client=None,
    *,
    max_tool_rounds: int = 1,
    planner_impl=None,
    verifier_impl=None,
):
    return build_graph(
        researcher_model=researcher_model,
        web_tool=web_tool,
        knowledge_client=knowledge_client or FakeKnowledgeClient(),
        writer_impl=writer_impl,
        planner_impl=planner_impl,
        verifier_impl=verifier_impl,
        max_tool_rounds=max_tool_rounds,
    )


def invoke_graph(graph, state):
    return graph.invoke(state, context=TEST_CONTEXT)


class FakeWriter:
    def __init__(self, report: str, events: list[str], error=None):
        self.report = report
        self.events = events
        self.received_payloads = []
        self.error = error

    def invoke(self, payload):
        self.events.append("writer")
        self.received_payloads.append(payload)
        if self.error is not None:
            raise self.error
        return self.report


def test_graph_executes_tool_and_passes_evidence_to_writer():
    events = []

    research_query = "LangGraph State 是什么？"

    tool_args = {
        "query": research_query,
    }

    researcher_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": tool_args,
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

    expected_evidence = [
        temporary_evidence(
            "https://langgraph.example/docs",
            "State stores graph execution data.",
            "Explains the role of State.",
        ),
        temporary_evidence(
            "https://langchain.example/docs",
            "Messages can be reduced automatically.",
            "Explains message reducer behavior.",
        ),
    ]

    expected_report = "这是最终研究报告。"
    expected_payloads = validate_evidence_list(expected_evidence)

    researcher_model = FakeResearcherModel(
        response=researcher_response,
        events=events,
    )

    tool = FakeTool(
        result=expected_evidence,
        events=events,
    )

    writer = FakeWriter(
        report=expected_report,
        events=events,
    )

    knowledge_client = FakeKnowledgeClient()
    graph = build_test_graph(
        researcher_model,
        tool,
        writer,
        knowledge_client,
    )

    result = invoke_graph(
        graph,
        {
            "messages": [
                HumanMessage(content=research_query)
            ]
        }
    )

    assert events == [
        "researcher",
        "execute_tool",
        "writer",
    ]

    assert tool.call_count == 1
    assert tool.received_args == [tool_args]
    assert researcher_model.bound_tool_options == {
        "parallel_tool_calls": True,
    }
    assert [tool.name for tool in researcher_model.bound_tools] == [
        "web_search",
        "knowledge_search",
    ]
    assert knowledge_client.calls == []

    assert len(writer.received_payloads) == 1

    writer_payload = writer.received_payloads[0]

    assert writer_payload["research_query"] == research_query
    assert writer_payload["evidence"] == expected_payloads
    assert len(
        writer_payload["evidence"]
    ) == 2
    assert (
    writer_payload["evidence"][0]["relevance_note"]
    == "Explains the role of State."
)

    assert result["report"] == expected_report

    final_messages = result["messages"]
    final_message = final_messages[-1]

    assert isinstance(final_message, AIMessage)
    assert final_message.content == expected_report


def test_graph_skips_tool_and_writer_receives_empty_evidence():
    events = []

    research_query = "LangGraph State 是什么？"

    researcher_response = AIMessage(
        content="No tool call is required.",
    )

    unused_evidence = {
        "source": "unused-source",
        "content": "This evidence should never reach the writer.",
    }

    expected_report = "这是无 Tool 路径的最终报告。"

    researcher_model = FakeResearcherModel(
        response=researcher_response,
        events=events,
    )

    tool = FakeTool(
        result=unused_evidence,
        events=events,
    )

    writer = FakeWriter(
        report=expected_report,
        events=events,
    )

    graph = build_test_graph(researcher_model, tool, writer)

    result = invoke_graph(
        graph,
        {
            "messages": [
                HumanMessage(content=research_query)
            ]
        }
    )

    assert events == [
        "researcher",
        "writer",
    ]

    assert tool.call_count == 0
    assert tool.received_args == []

    assert len(writer.received_payloads) == 1

    writer_payload = writer.received_payloads[0]

    assert writer_payload == {
        "research_query": research_query,
        "sub_questions": [research_query],
        "evidence": [],
    }

    assert result["report"] == expected_report
    assert result["citations"] == []

    final_messages = result["messages"]
    final_message = final_messages[-1]

    assert isinstance(final_message, AIMessage)
    assert final_message.content == expected_report


def test_invalid_evidence_item_does_not_reach_writer():
    events = []
    research_query = "LangGraph State 是什么？"
    researcher_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": {"query": research_query},
                "id": "call-invalid",
                "type": "tool_call",
            }
        ],
    )
    researcher_model = FakeResearcherModel(researcher_response, events)
    tool = FakeTool(
        [
            {
                "source_type": "temporary_research",
                "source_label": "fake-source",
                "content": 42,
                "provenance": {"url": "https://example.com"},
            }
        ],
        events,
    )
    writer = FakeWriter("This report must not be written.", events)
    graph = build_test_graph(researcher_model, tool, writer)

    with pytest.raises(ValueError, match="content"):
        invoke_graph(graph, {"messages": [HumanMessage(content=research_query)]})

    assert events == ["researcher", "execute_tool"]
    assert writer.received_payloads == []


class FakePlanner:
    """Deterministic planner stand-in that never touches the event log."""

    def __init__(self, sub_questions: list[str]):
        self.sub_questions = sub_questions
        self.received_payloads = []

    def invoke(self, payload):
        self.received_payloads.append(payload)
        return {"sub_questions": list(self.sub_questions)}


def test_planner_resets_state_from_previous_run():
    from researchflow.agent.plan import plan_research

    research_query = "新的研究问题"
    old_evidence = validate_evidence_list(
        [temporary_evidence(content="stale evidence")]
    )[0]
    planner = FakePlanner(["子问题 A", "子问题 B"])

    update = plan_research(
        {
            "messages": [HumanMessage(content=research_query)],
            "research_query": "旧问题",
            "sub_questions": ["旧子问题"],
            "tool_rounds": 2,
            "tool_calls_used": 4,
            "seen_tool_queries": ['["web_search", "{\\"query\\": \\"旧问题\\"}"]'],
            "evidence": [old_evidence],
            "citations": [{"citation_id": "c1"}],
            "verification": [{"citation_id": "c1", "support": "full", "reason": "x"}],
        },
        planner,
    )

    assert planner.received_payloads == [{"research_query": research_query}]
    assert update["research_query"] == research_query
    assert update["sub_questions"] == ["子问题 A", "子问题 B"]
    assert update["evidence"] == []
    assert update["tool_rounds"] == 0
    assert update["tool_calls_used"] == 0
    assert update["seen_tool_queries"] == []
    # A new run must not wipe the last successful Report/Citations pair: those
    # are only replaced by a successful Writer/Verifier pass.
    assert "citations" not in update
    assert "verification" not in update


def test_researcher_keeps_accumulated_evidence_across_rounds():
    events = []
    old_evidence = validate_evidence_list(
        [temporary_evidence(content="stale evidence")]
    )[0]
    researcher_model = FakeResearcherModel(
        AIMessage(content="No tool call is required."),
        events,
    )
    tool = FakeTool({}, events)

    update = researcher(
        {
            "messages": [HumanMessage(content="继续研究")],
            "evidence": [old_evidence],
            "tool_rounds": 1,
        },
        researcher_model,
        tool,
        FakeKnowledgeClient(),
        Runtime(context=TEST_CONTEXT),
    )

    # Evidence is the Writer's input and must survive every researcher turn;
    # only the Planner resets it (see test_planner_resets_state_from_previous_run).
    assert "evidence" not in update
    assert update["research_query"] == "继续研究"

def test_researcher_normalizes_text_blocks_and_ignores_invalid_blocks():
    events = []

    researcher_response = AIMessage(
        content="research complete",
    )

    researcher_model = FakeResearcherModel(
        response=researcher_response,
        events=events,
    )

    tool = FakeTool(
        result={},
        events=events,
    )

    writer = FakeWriter(
        report="report",
        events=events,
    )

    graph = build_test_graph(researcher_model, tool, writer)

    invoke_graph(
        graph,
        {
            "messages": [
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": "第一段",
                        },
                        {
                            "type": "image",
                            "url": "image-url",
                        },
                        {
                            "type": "text",
                            "text": "   ",
                        },
                        {
                            "type": "text",
                            "text": "第二段",
                        },
                        {
                            "type": "other",
                            "text": "ignore",
                        },
                    ]
                )
            ]
        }
    )

    assert writer.received_payloads == [
        {
            "research_query": "第一段\n\n第二段",
            "sub_questions": ["第一段\n\n第二段"],
            "evidence": [],
        }
    ]
    assert events == ["researcher", "writer"]


def test_researcher_rejects_empty_text_blocks_before_model_call():
    events = []

    researcher_model = FakeResearcherModel(
        response=AIMessage(
            content="should not happen",
        ),
        events=events,
    )

    tool = FakeTool(
        result={},
        events=events,
    )

    writer = FakeWriter(
        report="report",
        events=events,
    )

    graph = build_test_graph(researcher_model, tool, writer)

    with pytest.raises(
        ValueError,
        match="research query contains no valid text blocks",
    ):
        invoke_graph(
            graph,
            {
                "messages": [
                    HumanMessage(
                        content=[
                            {
                                "type": "image",
                                "url": "image-url",
                            },
                            {
                                "type": "text",
                                "text": "   ",
                            },
                            {
                                "type": "audio",
                            },
                        ]
                    )
                ]
            }
        )

    # normalization 失败发生在 model.invoke 前
    assert events == []


def test_normalize_research_query_strips_string_content():
    from researchflow.agent.graph import normalize_research_query

    assert normalize_research_query("  query  ") == "query"



def test_graph_executes_tool_with_empty_evidence_list():
    events = []

    research_query = "LangGraph State 是什么？"


    researcher_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": {
                    "query": research_query,
                },
                "id": "call-empty",
                "type": "tool_call",
            }
        ],
    )


    researcher_model = FakeResearcherModel(
        response=researcher_response,
        events=events,
    )


    tool = FakeTool(
        result=[],
        events=events,
    )


    writer = FakeWriter(
        report="没有找到相关证据。",
        events=events,
    )


    graph = build_test_graph(researcher_model, tool, writer)


    result = invoke_graph(
        graph,
        {
            "messages": [
                HumanMessage(
                    content=research_query
                )
            ]
        }
    )


    assert events == [
        "researcher",
        "execute_tool",
        "writer",
    ]


    assert tool.call_count == 1


    writer_payload = writer.received_payloads[0]


    assert writer_payload == {
        "research_query": research_query,
        "sub_questions": [research_query],
        "evidence": [],
    }


    assert result["report"] == (
        "没有找到相关证据。"
    )

def test_unknown_tool_call_is_rejected_before_execution():
    events = []

    research_query = "LangGraph State 是什么？"

    researcher_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": {"query": "must not run"},
                "id": "call-valid-before-unknown",
                "type": "tool_call",
            },
            {
                "name": "unknown_tool",
                "args": {
                    "query": research_query,
                },
                "id": "call-unknown",
                "type": "tool_call",
            }
        ],
    )

    researcher_model = FakeResearcherModel(
        response=researcher_response,
        events=events,
    )

    tool = FakeTool(
        result=[
            {
                "source": "fake",
                "content": "should never be returned",
            }
        ],
        events=events,
        name="web_search",
    )

    writer = FakeWriter(
        report="should never be generated",
        events=events,
    )

    graph = build_test_graph(researcher_model, tool, writer)

    with pytest.raises(
        ValueError,
        match="Unknown tool",
    ):
        invoke_graph(
            graph,
            {
                "messages": [
                    HumanMessage(
                        content=research_query
                    )
                ]
            }
        )

    # events records fake invoke() calls, so the rejected Tool is absent.
    assert events == ["researcher"]

    assert tool.call_count == 0

    assert writer.received_payloads == []


def test_graph_merges_evidence_from_multiple_calls_to_the_same_tool():
    events = []
    researcher_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": {"query": "first query"},
                "id": "call-1",
                "type": "tool_call",
            },
            {
                "name": "web_search",
                "args": {"query": "second query"},
                "id": "call-2",
                "type": "tool_call",
            },
        ],
    )
    evidence = [temporary_evidence()]
    researcher_model = FakeResearcherModel(researcher_response, events)
    tool = FakeTool(evidence, events)
    writer = FakeWriter("report", events)
    graph = build_test_graph(researcher_model, tool, writer)

    invoke_graph(
        graph,
        {"messages": [HumanMessage(content="research query")]}
    )

    assert sorted(tool.received_args, key=lambda item: item["query"]) == [
        {"query": "first query"},
        {"query": "second query"},
    ]
    assert writer.received_payloads == [
        {
            "research_query": "research query",
            "sub_questions": ["research query"],
            "evidence": validate_evidence_list(evidence) * 2,
        }
    ]


def test_graph_executes_web_and_knowledge_calls_in_model_order():
    events = []
    hit = KnowledgeHit(
        document_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        chunk_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        filename="project.md",
        content="Permanent Project evidence.",
        score=0.91,
    )
    knowledge_client = FakeKnowledgeClient([hit], events=events)
    web_tool = FakeTool([temporary_evidence()], events)
    researcher_model = FakeResearcherModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "web_search",
                    "args": {"query": "web first"},
                    "id": "call-web-1",
                    "type": "tool_call",
                },
                {
                    "name": "knowledge_search",
                    "args": {"query": "project", "limit": 2},
                    "id": "call-knowledge",
                    "type": "tool_call",
                },
                {
                    "name": "web_search",
                    "args": {"query": "web again"},
                    "id": "call-web-2",
                    "type": "tool_call",
                },
            ],
        ),
        events,
    )
    writer = FakeWriter("report", events)
    graph = build_test_graph(
        researcher_model,
        web_tool,
        writer,
        knowledge_client,
    )

    result = invoke_graph(graph, {"messages": [HumanMessage(content="research")]})

    assert events[0] == "researcher"
    assert events[-1] == "writer"
    assert sorted(events[1:-1]) == [
        "execute_tool",
        "execute_tool",
        "knowledge_search",
    ]
    assert knowledge_client.calls == [
        (TEST_CONTEXT.knowledge_scope, "project", 2),
    ]
    assert sorted(web_tool.received_args, key=lambda item: item["query"]) == [
        {"query": "web again"},
        {"query": "web first"},
    ]
    assert [
        item["source_type"] for item in writer.received_payloads[0]["evidence"]
    ] == ["temporary_research", "user_upload", "temporary_research"]
    assert [item["citation_id"] for item in result["citations"]] == [
        "c1", "c2", "c3"
    ]
    assert [item["source_type"] for item in result["citations"]] == [
        "temporary_research", "user_upload", "temporary_research"
    ]
    assert result["citations"][1]["provenance"]["chunk_id"] == str(hit.chunk_id)
    assert result["citations"][2] == {
        **result["citations"][0], "citation_id": "c3"
    }


def test_tool_failure_prevents_writer_and_partial_evidence_state():
    events = []
    web_tool = FakeTool([temporary_evidence()], events)
    knowledge_client = FakeKnowledgeClient(
        events=events,
        error=KnowledgeSearchError("Knowledge search unavailable"),
    )
    researcher_model = FakeResearcherModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "web_search",
                    "args": {"query": "web runs first"},
                    "id": "call-web",
                    "type": "tool_call",
                },
                {
                    "name": "knowledge_search",
                    "args": {"query": "fails second"},
                    "id": "call-knowledge",
                    "type": "tool_call",
                },
            ],
        ),
        events,
    )
    writer = FakeWriter("must not run", events)
    graph = build_test_graph(
        researcher_model,
        web_tool,
        writer,
        knowledge_client,
    )

    with pytest.raises(KnowledgeSearchError, match="unavailable"):
        invoke_graph(graph, {"messages": [HumanMessage(content="research")]})

    assert events[0] == "researcher"
    assert sorted(events[1:]) == ["execute_tool", "knowledge_search"]
    assert writer.received_payloads == []


def test_graph_requires_knowledge_scope_run_context_before_model_call():
    events = []
    researcher_model = FakeResearcherModel(
        AIMessage(content="No tool call."),
        events,
    )
    graph = build_test_graph(
        researcher_model,
        FakeTool([], events),
        FakeWriter("must not run", events),
    )

    with pytest.raises(ValueError, match="knowledge_scope"):
        graph.invoke({"messages": [HumanMessage(content="research")]})

    assert events == []


def test_agent_context_is_frozen_and_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="frozen"):
        TEST_CONTEXT.knowledge_scope = KnowledgeScope(
            user_id="22222222-2222-2222-2222-222222222222",
            project_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        )

    with pytest.raises(ValidationError, match="extra_forbidden"):
        AgentContext.model_validate(
            {
                "knowledge_scope": TEST_CONTEXT.knowledge_scope,
                "thread_id": "not-authority",
            }
        )


@pytest.mark.parametrize("failure", ["mapping", "writer", "report_type"])
def test_checkpoint_retains_matching_final_output_until_next_success(
    monkeypatch, failure
):
    events = []
    researcher_model = FakeResearcherModel(
        AIMessage(
            content="",
            tool_calls=[{
                "name": "web_search",
                "args": {"query": "research"},
                "id": "call-first",
                "type": "tool_call",
            }],
        ),
        events,
    )
    tool = FakeTool([temporary_evidence(content="First evidence")], events)
    writer = FakeWriter("First successful report", events)
    graph = build_test_graph(researcher_model, tool, writer).builder.compile(
        checkpointer=InMemorySaver()
    )
    config = {"configurable": {"thread_id": "fresh-citation-regression"}}

    first = graph.invoke(
        {"messages": [HumanMessage(content="First query")]},
        config,
        context=TEST_CONTEXT,
    )

    assert set(first) == {
        "messages",
        "report",
        "citations",
        "tool_rounds",
        "research_query",
        "sub_questions",
        "verification",
    }
    assert first["report"] == "First successful report"
    assert first["messages"][-1].content == first["report"]
    assert first["citations"] == [{
        "citation_id": "c1",
        "source_type": "temporary_research",
        "source_label": "https://example.com",
        "excerpt": "First evidence",
        "provenance": {"url": "https://example.com/"},
    }]

    tool.result = [temporary_evidence(content="Evidence for failed run")]
    writer.report = "Must not become a final report"
    with monkeypatch.context() as patcher:
        if failure == "mapping":
            def fail_mapping(evidence):
                raise ValueError("test mapping failure")

            patcher.setattr(graph_module, "map_evidence_to_citations", fail_mapping)
            error_type, error_message = ValueError, "test mapping failure"
        elif failure == "writer":
            patcher.setattr(writer, "error", RuntimeError("test Writer failure"))
            error_type, error_message = RuntimeError, "test Writer failure"
        else:
            patcher.setattr(writer, "report", {"invalid": "structured report"})
            error_type, error_message = ValueError, "string report"

        snapshots = []
        with pytest.raises(error_type, match=error_message):
            for state in graph.stream(
                {"messages": [HumanMessage(content="Failing query")]},
                config,
                context=TEST_CONTEXT,
                stream_mode="values",
            ):
                snapshots.append(state)

    assert len(snapshots) >= 2
    for state in [*snapshots, graph.get_state(config).values]:
        assert state["report"] == first["report"]
        assert state["citations"] == first["citations"]
        assert all(
            message.content != "Must not become a final report"
            for message in state["messages"]
        )
    assert len(writer.received_payloads) == (1 if failure == "mapping" else 2)

    researcher_model.response = AIMessage(content="No tool needed this time.")
    writer.report = "Latest successful report without evidence"
    latest = graph.invoke(
        {"messages": [HumanMessage(content="New no-Tool query")]},
        config,
        context=TEST_CONTEXT,
    )

    assert set(latest) == {
        "messages",
        "report",
        "citations",
        "tool_rounds",
        "research_query",
        "sub_questions",
        "verification",
    }
    assert latest["report"] == writer.report
    assert latest["messages"][-1].content == latest["report"]
    assert latest["citations"] == []
    checkpoint = graph.get_state(config).values
    assert checkpoint["report"] == latest["report"]
    assert checkpoint["citations"] == []
    assert writer.received_payloads[-1] == {
        "research_query": "New no-Tool query",
        "sub_questions": ["New no-Tool query"],
        "evidence": [],
    }


def test_execute_tool_runs_multiple_calls_in_parallel_and_preserves_order():
    import contextvars
    import threading
    from langchain_core.messages import ToolMessage

    trace_var: contextvars.ContextVar[str] = contextvars.ContextVar(
        "trace_var", default="missing"
    )
    barrier = threading.Barrier(2, timeout=2.0)
    second_finished = threading.Event()
    completion_order: list[str] = []
    observed_context: dict[str, str] = {}
    lock = threading.Lock()

    class ConcurrentWebTool:
        name = "web_search"

        def invoke(self, args):
            query = args["query"]
            # Both calls must enter invoke() simultaneously or barrier times out.
            barrier.wait()
            with lock:
                observed_context[query] = trace_var.get()
            if query == "slow-first":
                assert second_finished.wait(timeout=2.0)
                with lock:
                    completion_order.append(query)
                return [temporary_evidence("https://first.example", "first-body")]
            with lock:
                completion_order.append(query)
            second_finished.set()
            return [temporary_evidence("https://second.example", "second-body")]

    events: list[str] = []
    researcher_model = FakeResearcherModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "web_search",
                    "args": {"query": "slow-first"},
                    "id": "call-first",
                    "type": "tool_call",
                },
                {
                    "name": "web_search",
                    "args": {"query": "fast-second"},
                    "id": "call-second",
                    "type": "tool_call",
                },
            ],
        ),
        events,
    )
    writer = FakeWriter("report", events)
    graph = build_test_graph(researcher_model, ConcurrentWebTool(), writer)

    token = trace_var.set("propagated-trace")
    try:
        result = invoke_graph(graph, {"messages": [HumanMessage(content="parallel")]})
    finally:
        trace_var.reset(token)

    assert completion_order == ["fast-second", "slow-first"]
    assert observed_context == {
        "slow-first": "propagated-trace",
        "fast-second": "propagated-trace",
    }
    assert [
        item["content"] for item in writer.received_payloads[0]["evidence"]
    ] == ["first-body", "second-body"]
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_messages] == ["call-first", "call-second"]


def test_single_tool_call_runs_on_caller_thread_without_pool():
    import threading
    from researchflow.agent.graph import execute_tool

    caller_thread = threading.get_ident()
    observed_threads: list[int] = []

    class ThreadRecordingTool:
        name = "web_search"

        def invoke(self, args):
            observed_threads.append(threading.get_ident())
            return [temporary_evidence()]

    execute_tool(
        {
            "messages": [
                HumanMessage(content="q"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "web_search",
                            "args": {"query": "only-one"},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                ),
            ]
        },
        ThreadRecordingTool(),
        FakeKnowledgeClient(),
        Runtime(context=TEST_CONTEXT),
    )

    assert observed_threads == [caller_thread]


def test_recover_tool_errors_degrades_runtime_failure_without_losing_sibling_evidence():
    from langchain_core.messages import ToolMessage

    events: list[str] = []
    web_tool = FakeTool([temporary_evidence(content="survived")], events)
    knowledge_client = FakeKnowledgeClient(
        events=events,
        error=KnowledgeSearchError("Knowledge search unavailable"),
    )
    researcher_model = FakeResearcherModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "web_search",
                    "args": {"query": "web succeeds"},
                    "id": "call-web",
                    "type": "tool_call",
                },
                {
                    "name": "knowledge_search",
                    "args": {"query": "backend down"},
                    "id": "call-knowledge",
                    "type": "tool_call",
                },
            ],
        ),
        events,
    )
    writer = FakeWriter("degraded report [c1]", events)
    graph = build_graph(
        researcher_model=researcher_model,
        web_tool=web_tool,
        knowledge_client=knowledge_client,
        writer_impl=writer,
        max_tool_rounds=1,
        recover_tool_errors=True,
    )

    result = invoke_graph(graph, {"messages": [HumanMessage(content="research")]})

    assert result["report"] == "degraded report [c1]"
    assert [item["content"] for item in writer.received_payloads[0]["evidence"]] == [
        "survived"
    ]
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_messages] == ["call-web", "call-knowledge"]
    assert tool_messages[0].content == "Research evidence collected successfully."
    assert tool_messages[1].status == "error"
    assert "Tool error (KnowledgeSearchError): Knowledge search unavailable" in tool_messages[1].content


def test_recover_tool_errors_catches_invalid_tool_args_but_still_rejects_unknown_tools():
    from langchain_core.messages import ToolMessage

    events: list[str] = []
    web_tool = FakeTool([temporary_evidence()], events)
    bad_args_model = FakeResearcherModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "knowledge_search",
                    "args": {"query": "valid", "limit": 99},
                    "id": "call-bad-args",
                    "type": "tool_call",
                }
            ],
        ),
        events,
    )
    writer = FakeWriter("report after bad args", events)
    graph = build_graph(
        researcher_model=bad_args_model,
        web_tool=web_tool,
        knowledge_client=FakeKnowledgeClient(),
        writer_impl=writer,
        max_tool_rounds=1,
        recover_tool_errors=True,
    )

    result = invoke_graph(graph, {"messages": [HumanMessage(content="research")]})
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert tool_messages[0].status == "error"
    assert "Tool error" in tool_messages[0].content

    unknown_model = FakeResearcherModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "nonexistent_tool",
                    "args": {"query": "x"},
                    "id": "call-unknown",
                    "type": "tool_call",
                }
            ],
        ),
        events,
    )
    unknown_graph = build_graph(
        researcher_model=unknown_model,
        web_tool=web_tool,
        knowledge_client=FakeKnowledgeClient(),
        writer_impl=writer,
        max_tool_rounds=1,
        recover_tool_errors=True,
    )
    with pytest.raises(ValueError, match="Unknown tool"):
        invoke_graph(unknown_graph, {"messages": [HumanMessage(content="research")]})
