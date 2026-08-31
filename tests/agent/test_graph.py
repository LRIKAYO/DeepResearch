import pytest

from langchain_core.messages import AIMessage, HumanMessage

from researchflow.agent.graph import build_graph, researcher


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
    def __init__(self, result: object, events: list[str], name: str="fake_search"):
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


class FakeWriter:
    def __init__(self, report: str, events: list[str]):
        self.report = report
        self.events = events
        self.received_payloads = []

    def invoke(self, payload):
        self.events.append("writer")
        self.received_payloads.append(payload)
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
                "name": "fake_search",
                "args": tool_args,
                "id": "call-1",
                "type": "tool_call",
            }
        ],
    )

    expected_evidence = [
        {
            "source": "langgraph-docs",
            "content": "State stores graph execution data.",
            "relevance_note": (
                "Explains the role of State."
            ),
        },
        {
            "source": "langchain-docs",
            "content": "Messages can be reduced automatically.",
            "relevance_note": (
                "Explains message reducer behavior."
            ),
        },
    ]

    expected_report = "这是最终研究报告。"

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

    graph = build_graph(
        researcher_model=researcher_model,
        tool=tool,
        writer_impl=writer,
    )

    result = graph.invoke(
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
        "parallel_tool_calls": False,
    }

    assert len(writer.received_payloads) == 1

    writer_payload = writer.received_payloads[0]

    assert writer_payload["research_query"] == research_query
    assert writer_payload["evidence"] == expected_evidence
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

    graph = build_graph(
        researcher_model=researcher_model,
        tool=tool,
        writer_impl=writer,
    )

    result = graph.invoke(
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
        "evidence": [],
    }

    assert result["report"] == expected_report

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
                "name": "fake_search",
                "args": {"query": research_query},
                "id": "call-invalid",
                "type": "tool_call",
            }
        ],
    )
    researcher_model = FakeResearcherModel(researcher_response, events)
    tool = FakeTool([{"source": "fake-source", "content": 42}], events)
    writer = FakeWriter("This report must not be written.", events)
    graph = build_graph(researcher_model, tool, writer)

    with pytest.raises(ValueError, match="content"):
        graph.invoke({"messages": [HumanMessage(content=research_query)]})

    assert events == ["researcher", "execute_tool"]
    assert writer.received_payloads == []


def test_researcher_clears_evidence_from_previous_run():
    events = []
    research_query = "新的研究问题"
    old_evidence = {"source": "old-source", "content": "stale evidence"}
    researcher_model = FakeResearcherModel(
        AIMessage(content="No tool call is required."),
        events,
    )
    tool = FakeTool({}, events)

    update = researcher(
        {
            "messages": [HumanMessage(content=research_query)],
            "evidence": [old_evidence],
        },
        researcher_model,
        tool,
    )

    assert update["evidence"] == []

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

    graph = build_graph(
        researcher_model=researcher_model,
        tool=tool,
        writer_impl=writer,
    )

    graph.invoke(
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

    graph = build_graph(
        researcher_model=researcher_model,
        tool=tool,
        writer_impl=writer,
    )

    with pytest.raises(
        ValueError,
        match="research query contains no valid text blocks",
    ):
        graph.invoke(
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
                "name": "fake_search",
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


    graph = build_graph(
        researcher_model=researcher_model,
        tool=tool,
        writer_impl=writer,
    )


    result = graph.invoke(
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
        name="fake_search",
    )

    writer = FakeWriter(
        report="should never be generated",
        events=events,
    )

    graph = build_graph(
        researcher_model=researcher_model,
        tool=tool,
        writer_impl=writer,
    )

    with pytest.raises(
        ValueError,
        match="Unknown tool",
    ):
        graph.invoke(
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
                "name": "fake_search",
                "args": {"query": "first query"},
                "id": "call-1",
                "type": "tool_call",
            },
            {
                "name": "fake_search",
                "args": {"query": "second query"},
                "id": "call-2",
                "type": "tool_call",
            },
        ],
    )
    evidence = [{"source": "fake", "content": "result"}]
    researcher_model = FakeResearcherModel(researcher_response, events)
    tool = FakeTool(evidence, events)
    writer = FakeWriter("report", events)
    graph = build_graph(researcher_model, tool, writer)

    graph.invoke(
        {"messages": [HumanMessage(content="research query")]}
    )

    assert tool.received_args == [
        {"query": "first query"},
        {"query": "second query"},
    ]
    assert writer.received_payloads == [
        {"research_query": "research query", "evidence": evidence * 2}
    ]
