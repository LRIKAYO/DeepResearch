"""Bounded multi-round research loop, planner wiring, and verifier integration."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from researchflow.agent.evidence import (
    TemporaryResearchEvidence,
    TemporaryWebProvenance,
    validate_evidence_list,
)
from researchflow.agent.graph import build_graph, researcher
from researchflow.agent.knowledge_search import KnowledgeScope
from researchflow.agent.state import AgentContext


TEST_CONTEXT = AgentContext(
    knowledge_scope=KnowledgeScope(
        user_id="11111111-1111-1111-1111-111111111111",
        project_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
)


def web_evidence(content: str) -> TemporaryResearchEvidence:
    return TemporaryResearchEvidence(
        source_label=f"https://example.com/{content}",
        content=content,
        provenance=TemporaryWebProvenance(url=f"https://example.com/{content}"),
    )


def tool_call(call_id: str = "call-1", query: str = "q") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": {"query": query},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


class ScriptedModel:
    """Returns scripted responses; records how many times tools were bound."""

    def __init__(self, responses: list[AIMessage]):
        self.responses = list(responses)
        self.invocations = 0
        self.bind_calls = 0
        self.bound_tools = None
        self.received_messages: list[list] = []

    def bind_tools(self, tools, **kwargs):
        self.bind_calls += 1
        self.bound_tools = list(tools)
        return self

    def invoke(self, messages):
        self.received_messages.append(list(messages))
        index = min(self.invocations, len(self.responses) - 1)
        self.invocations += 1
        return self.responses[index]


class QueueTool:
    """web_search stand-in that returns a different result per call."""

    def __init__(self, results: list[list]):
        self.results = list(results)
        self.name = "web_search"
        self.invoke_count = 0
        self.received_args = []

    def invoke(self, args):
        self.received_args.append(args)
        index = min(self.invoke_count, len(self.results) - 1)
        self.invoke_count += 1
        return self.results[index]


class EmptyKnowledgeClient:
    def search(self, *, scope, query, limit):
        return []


class RecordingWriter:
    def __init__(self, report: str = "report"):
        self.report = report
        self.payloads: list[dict] = []

    def invoke(self, payload):
        self.payloads.append(payload)
        return self.report


class FixedPlanner:
    def __init__(self, sub_questions: list[str]):
        self.sub_questions = sub_questions
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        return {"sub_questions": list(self.sub_questions)}


class FakeVerifier:
    def __init__(self, result):
        self.result = result
        self.payloads: list[dict] = []

    def invoke(self, payload):
        self.payloads.append(payload)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def build(model, tool, writer, **kwargs):
    return build_graph(
        researcher_model=model,
        web_tool=tool,
        knowledge_client=EmptyKnowledgeClient(),
        writer_impl=writer,
        **kwargs,
    )


def invoke(graph, query: str = "研究问题"):
    return graph.invoke(
        {"messages": [HumanMessage(content=query)]},
        context=TEST_CONTEXT,
    )


# --- multi-round loop -------------------------------------------------------


def test_graph_runs_multiple_tool_rounds_and_accumulates_evidence():
    model = ScriptedModel(
        [tool_call("call-1", "first"), tool_call("call-2", "second"), AIMessage(content="READY")]
    )
    tool = QueueTool([[web_evidence("round-one")], [web_evidence("round-two")]])
    writer = RecordingWriter()

    result = invoke(build(model, tool, writer, max_tool_rounds=3))

    assert model.invocations == 3
    assert tool.invoke_count == 2
    assert tool.received_args == [{"query": "first"}, {"query": "second"}]
    assert [item["content"] for item in writer.payloads[0]["evidence"]] == [
        "round-one",
        "round-two",
    ]
    assert [item["citation_id"] for item in result["citations"]] == ["c1", "c2"]
    assert len(writer.payloads) == 1


def test_graph_stops_at_the_round_budget_and_still_writes():
    responses = [tool_call(f"call-{index}", f"q-{index}") for index in range(1, 5)]
    model = ScriptedModel(responses)
    tool = QueueTool([[web_evidence(f"e{index}")] for index in range(1, 4)])
    writer = RecordingWriter()

    result = invoke(build(model, tool, writer, max_tool_rounds=2))

    # Two rounds run, then routing goes straight to the Writer: the loop never
    # spends an extra model call once the budget is gone.
    assert tool.invoke_count == 2
    assert model.invocations == 2
    assert model.bind_calls == 2
    assert len(writer.payloads[0]["evidence"]) == 2
    assert result["report"] == writer.report


def test_researcher_without_budget_gets_no_tool_schema():
    model = ScriptedModel([AIMessage(content="READY")])

    researcher(
        {
            "messages": [HumanMessage(content="研究问题")],
            "research_query": "研究问题",
            "tool_rounds": 3,
        },
        model,
        QueueTool([[]]),
        EmptyKnowledgeClient(),
        Runtime(context=TEST_CONTEXT),
        max_tool_rounds=3,
    )

    assert model.bind_calls == 0
    assert model.invocations == 1


def test_graph_uses_only_one_round_when_the_model_stops_immediately():
    model = ScriptedModel([AIMessage(content="READY")])
    tool = QueueTool([[web_evidence("unused")]])
    writer = RecordingWriter()

    result = invoke(build(model, tool, writer, max_tool_rounds=3))

    assert tool.invoke_count == 0
    assert result["citations"] == []
    assert model.bind_calls == 1


# --- researcher context -----------------------------------------------------


def test_researcher_receives_the_plan_and_the_evidence_so_far():
    model = ScriptedModel([AIMessage(content="READY")])
    state = {
        "messages": [HumanMessage(content="研究问题")],
        "research_query": "研究问题",
        "sub_questions": ["子问题一", "子问题二"],
        "evidence": validate_evidence_list([web_evidence("已有证据")]),
        "tool_rounds": 1,
    }

    researcher(
        state,
        model,
        QueueTool([[]]),
        EmptyKnowledgeClient(),
        Runtime(context=TEST_CONTEXT),
        max_tool_rounds=3,
    )

    context_message = model.received_messages[0][0]
    assert isinstance(context_message, SystemMessage)
    assert "子问题一" in context_message.content
    assert "[c1]" in context_message.content
    assert "已有证据" in context_message.content
    assert "1 of 3" in context_message.content


def test_researcher_prepends_its_system_prompt():
    model = ScriptedModel([AIMessage(content="READY")])

    researcher(
        {"messages": [HumanMessage(content="研究问题")], "research_query": "研究问题"},
        model,
        QueueTool([[]]),
        EmptyKnowledgeClient(),
        Runtime(context=TEST_CONTEXT),
        system_prompt="你是研究员",
    )

    assert model.received_messages[0][0].content == "你是研究员"


def test_researcher_does_not_add_context_on_the_first_turn():
    model = ScriptedModel([AIMessage(content="READY")])

    researcher(
        {"messages": [HumanMessage(content="研究问题")], "research_query": "研究问题"},
        model,
        QueueTool([[]]),
        EmptyKnowledgeClient(),
        Runtime(context=TEST_CONTEXT),
    )

    assert len(model.received_messages[0]) == 1


# --- planner and verifier wiring -------------------------------------------


def test_graph_passes_planner_sub_questions_to_the_writer():
    model = ScriptedModel([AIMessage(content="READY")])
    writer = RecordingWriter()
    planner = FixedPlanner(["子问题一", "子问题二"])

    result = invoke(build(model, QueueTool([[]]), writer, planner_impl=planner))

    assert planner.calls == 1
    assert writer.payloads[0]["sub_questions"] == ["子问题一", "子问题二"]
    assert result["sub_questions"] == ["子问题一", "子问题二"]


def test_graph_returns_verifier_verdicts():
    model = ScriptedModel([tool_call("call-1"), AIMessage(content="READY")])
    tool = QueueTool([[web_evidence("证据")]])
    verifier = FakeVerifier(
        {"results": [{"citation_id": "c1", "support": "full", "reason": "一致"}]}
    )

    result = invoke(build(model, tool, RecordingWriter("报告 [c1]"), verifier_impl=verifier))

    assert len(verifier.payloads) == 1
    assert result["verification"] == [
        {"citation_id": "c1", "support": "full", "reason": "一致"}
    ]


def test_a_verifier_failure_keeps_the_report_and_citations():
    model = ScriptedModel([tool_call("call-1"), AIMessage(content="READY")])
    tool = QueueTool([[web_evidence("证据")]])
    verifier = FakeVerifier(RuntimeError("provider down"))

    result = invoke(build(model, tool, RecordingWriter("报告 [c1]"), verifier_impl=verifier))

    assert result["report"] == "报告 [c1]"
    assert len(result["citations"]) == 1
    assert result["verification"] == []


# --- configuration guards ---------------------------------------------------


def test_compiled_graph_exposes_the_research_topology():
    graph = build(
        ScriptedModel([AIMessage(content="READY")]),
        QueueTool([[]]),
        RecordingWriter(),
    )
    drawable = graph.get_graph()

    assert set(drawable.nodes) == {
        "__start__",
        "planner",
        "researcher",
        "execute_tool",
        "writer",
        "verifier",
        "persist",
        "__end__",
    }

    edges = {(edge.source, edge.target) for edge in drawable.edges}

    assert ("__start__", "planner") in edges
    assert ("planner", "researcher") in edges
    assert ("execute_tool", "researcher") in edges
    assert ("writer", "verifier") in edges
    assert ("verifier", "persist") in edges
    assert ("persist", "__end__") in edges


@pytest.mark.parametrize("value", [0, -1, 11, 2.5, True])
def test_build_graph_rejects_invalid_round_budgets(value):
    with pytest.raises(ValueError, match="max_tool_rounds"):
        build(
            ScriptedModel([AIMessage(content="READY")]),
            QueueTool([[]]),
            RecordingWriter(),
            max_tool_rounds=value,
        )


def test_output_exposes_tool_rounds_because_the_ui_shows_it():
    model = ScriptedModel(
        [tool_call("call-1"), tool_call("call-2"), AIMessage(content="READY")]
    )
    tool = QueueTool([[web_evidence("a")], [web_evidence("b")], [web_evidence("c")]])

    result = invoke(build(model, tool, RecordingWriter(), max_tool_rounds=3))

    assert result["tool_rounds"] == 2


def test_output_reports_zero_rounds_when_no_tool_was_used():
    result = invoke(
        build(
            ScriptedModel([AIMessage(content="READY")]),
            QueueTool([[]]),
            RecordingWriter(),
        )
    )

    assert result["tool_rounds"] == 0

# --- provider argument shapes ------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"query": "q"}, {"query": "q"}),
        ('{"query": "q"}', {"query": "q"}),
        ({"arguments": '{"query": "q"}'}, {"query": "q"}),
        ({"arguments": "not json"}, {"arguments": "not json"}),
        ("plain string", "plain string"),
        ({"arguments": "[1, 2]"}, {"arguments": "[1, 2]"}),
    ],
)
def test_normalize_tool_args_unwraps_known_provider_shapes(raw, expected):
    from researchflow.agent.graph import normalize_tool_args

    assert normalize_tool_args(raw) == expected


def test_graph_survives_a_tool_call_wrapped_in_an_arguments_object():
    """Some OpenAI-compatible providers nest the JSON string under "arguments"."""

    wrapped = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "web_search",
                "args": {"arguments": '{"query": "wrapped"}'},
                "id": "call-wrapped",
                "type": "tool_call",
            }
        ],
    )
    model = ScriptedModel([wrapped, AIMessage(content="READY")])
    tool = QueueTool([[web_evidence("wrapped evidence")]])
    writer = RecordingWriter()

    result = invoke(build(model, tool, writer))

    assert tool.received_args == [{"query": "wrapped"}]
    assert tool.invoke_count == 1
    assert result["report"] == writer.report


# --- total tool-call budget & deduplication ---------------------------------


@pytest.mark.parametrize("value", [0, -1, 31, 2.5, True])
def test_build_graph_rejects_invalid_tool_call_budgets(value):
    with pytest.raises(ValueError, match="max_tool_calls"):
        build(
            ScriptedModel([AIMessage(content="READY")]),
            QueueTool([[]]),
            RecordingWriter(),
            max_tool_calls=value,
        )


def test_researcher_without_tool_call_budget_gets_no_tool_schema():
    model = ScriptedModel([AIMessage(content="READY")])

    researcher(
        {
            "messages": [HumanMessage(content="研究问题")],
            "research_query": "研究问题",
            "sub_questions": ["子问题一"],
            "tool_rounds": 1,
            "tool_calls_used": 2,
        },
        model,
        QueueTool([[]]),
        EmptyKnowledgeClient(),
        Runtime(context=TEST_CONTEXT),
        max_tool_rounds=3,
        max_tool_calls=2,
    )

    assert model.bind_calls == 0
    assert model.invocations == 1
    context_message = model.received_messages[0][0]
    assert "Tool calls used: 2 of 2." in context_message.content


def test_excess_tool_calls_in_one_turn_are_capped_without_orphan_ids():
    from langchain_core.messages import ToolMessage

    burst = AIMessage(
        content="",
        tool_calls=[
            {"name": "web_search", "args": {"query": "q1"}, "id": "call-1", "type": "tool_call"},
            {"name": "web_search", "args": {"query": "q2"}, "id": "call-2", "type": "tool_call"},
            {"name": "web_search", "args": {"query": "q3"}, "id": "call-3", "type": "tool_call"},
        ],
    )
    model = ScriptedModel([burst, AIMessage(content="unused")])
    tool = QueueTool([[web_evidence("e1")], [web_evidence("e2")], [web_evidence("e3")]])
    writer = RecordingWriter("capped report")

    result = invoke(build(model, tool, writer, max_tool_rounds=3, max_tool_calls=2))

    # Only 2 calls executed; route_after_tools sends straight to writer without a 2nd model call.
    assert tool.invoke_count == 2
    assert model.invocations == 1
    assert [item["content"] for item in writer.payloads[0]["evidence"]] == ["e1", "e2"]

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_messages] == ["call-1", "call-2", "call-3"]
    assert tool_messages[2].content == "Skipped: tool-call budget exhausted."


def test_duplicate_queries_across_rounds_are_skipped_without_reinvoking_tool():
    from langchain_core.messages import ToolMessage

    model = ScriptedModel(
        [
            tool_call("call-1", "  same query  "),
            tool_call("call-2", "same query"),
            AIMessage(content="READY"),
        ]
    )
    tool = QueueTool([[web_evidence("only-once")], [web_evidence("should-not-run")]])
    writer = RecordingWriter()

    result = invoke(build(model, tool, writer, max_tool_rounds=3))

    assert tool.invoke_count == 1
    assert result["tool_rounds"] == 2
    assert [item["content"] for item in writer.payloads[0]["evidence"]] == ["only-once"]
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages[1].content == "Duplicate tool query skipped; already executed in this run."


def test_cross_round_duplicate_provenance_is_deduplicated():
    from uuid import UUID
    from researchflow.agent.knowledge_search import KnowledgeHit

    doc_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    chunk_1 = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    chunk_2 = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    class MultiRoundKnowledgeClient:
        def __init__(self):
            self.calls = 0

        def search(self, *, scope, query, limit):
            self.calls += 1
            if self.calls == 1:
                return [
                    KnowledgeHit(
                        document_id=doc_id,
                        chunk_id=chunk_1,
                        filename="doc.md",
                        content="chunk one",
                        score=0.9,
                    )
                ]
            return [
                KnowledgeHit(
                    document_id=doc_id,
                    chunk_id=chunk_1,
                    filename="doc.md",
                    content="chunk one",
                    score=0.88,
                ),
                KnowledgeHit(
                    document_id=doc_id,
                    chunk_id=chunk_2,
                    filename="doc.md",
                    content="chunk two",
                    score=0.85,
                ),
            ]

    round_1 = AIMessage(
        content="",
        tool_calls=[
            {"name": "web_search", "args": {"query": "web-1"}, "id": "w1", "type": "tool_call"},
            {"name": "knowledge_search", "args": {"query": "k-1"}, "id": "k1", "type": "tool_call"},
        ],
    )
    round_2 = AIMessage(
        content="",
        tool_calls=[
            {"name": "web_search", "args": {"query": "web-2"}, "id": "w2", "type": "tool_call"},
            {"name": "knowledge_search", "args": {"query": "k-2"}, "id": "k2", "type": "tool_call"},
        ],
    )
    model = ScriptedModel([round_1, round_2, AIMessage(content="READY")])
    shared_web = web_evidence("shared-web")
    unique_web = web_evidence("unique-web")
    tool = QueueTool([[shared_web], [shared_web, unique_web]])
    writer = RecordingWriter()

    graph = build_graph(
        researcher_model=model,
        web_tool=tool,
        knowledge_client=MultiRoundKnowledgeClient(),
        writer_impl=writer,
        max_tool_rounds=3,
    )
    result = invoke(graph)

    contents = [item["content"] for item in writer.payloads[0]["evidence"]]
    assert contents == ["shared-web", "chunk one", "unique-web", "chunk two"]
    assert [item["citation_id"] for item in result["citations"]] == ["c1", "c2", "c3", "c4"]
