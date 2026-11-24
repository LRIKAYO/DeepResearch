import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from researchflow.agent import runtime
from researchflow.agent.plan import ResearchPlan
from researchflow.agent.verification import VerificationBatch


class RecordingModel:
    """Minimal structured-output capable stand-in for ChatOpenAI."""

    def __init__(self):
        self.structured_schemas = []

    def with_structured_output(self, schema):
        self.structured_schemas.append(schema)
        return RunnableLambda(lambda value: value)


def test_create_runtime_rejects_missing_model_key(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    with pytest.raises(ValueError, match="SILICONFLOW_API_KEY"):
        runtime.create_runtime()


def test_create_runtime_wires_one_model_to_graph(monkeypatch):
    model = object()
    web_tool = object()
    knowledge_client = object()
    writer = object()
    planner = object()
    verifier = object()
    persister = object()
    graph = object()
    captured = {}

    monkeypatch.setattr(runtime, "create_model", lambda: model)
    monkeypatch.setattr(runtime, "create_web_search", lambda: web_tool)
    monkeypatch.setattr(
        runtime,
        "create_knowledge_client",
        lambda: knowledge_client,
    )
    monkeypatch.setattr(runtime, "create_writer", lambda received: writer)
    monkeypatch.setattr(runtime, "create_planner", lambda received: planner)
    monkeypatch.setattr(runtime, "create_verifier", lambda received: verifier)
    monkeypatch.setattr(runtime, "create_report_persister", lambda: persister)

    def fake_build_graph(**kwargs):
        captured.update(kwargs)
        return graph

    monkeypatch.setattr(runtime, "build_graph", fake_build_graph)

    assert runtime.create_runtime() is graph

    assert captured["researcher_model"] is model
    assert captured["web_tool"] is web_tool
    assert captured["knowledge_client"] is knowledge_client
    assert captured["writer_impl"] is writer
    assert captured["planner_impl"] is planner
    assert captured["verifier_impl"] is verifier
    assert captured["persist_impl"] is persister
    assert captured["max_tool_rounds"] == 3
    assert captured["max_tool_calls"] == 6
    assert captured["recover_tool_errors"] is True
    assert "bounded" in captured["researcher_system_prompt"].lower()


def test_create_planner_uses_structured_research_plan():
    model = RecordingModel()

    runtime.create_planner(model)

    assert model.structured_schemas == [ResearchPlan]


def test_create_verifier_uses_structured_verification_batch():
    model = RecordingModel()

    runtime.create_verifier(model)

    assert model.structured_schemas == [VerificationBatch]


def test_read_max_tool_rounds_defaults_to_three(monkeypatch):
    monkeypatch.delenv("RESEARCHFLOW_MAX_TOOL_ROUNDS", raising=False)

    assert runtime.read_max_tool_rounds() == 3


def test_read_max_tool_rounds_reads_the_environment(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_MAX_TOOL_ROUNDS", "5")

    assert runtime.read_max_tool_rounds() == 5


@pytest.mark.parametrize("raw", ["0", "11", "-1"])
def test_read_max_tool_rounds_rejects_out_of_range(monkeypatch, raw):
    monkeypatch.setenv("RESEARCHFLOW_MAX_TOOL_ROUNDS", raw)

    with pytest.raises(ValueError, match="RESEARCHFLOW_MAX_TOOL_ROUNDS"):
        runtime.read_max_tool_rounds()


def test_read_max_tool_rounds_rejects_non_integer(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_MAX_TOOL_ROUNDS", "three")

    with pytest.raises(ValueError, match="RESEARCHFLOW_MAX_TOOL_ROUNDS"):
        runtime.read_max_tool_rounds()


def test_read_max_tool_calls_defaults_to_six(monkeypatch):
    monkeypatch.delenv("RESEARCHFLOW_MAX_TOOL_CALLS", raising=False)

    assert runtime.read_max_tool_calls() == 6


def test_read_max_tool_calls_reads_the_environment(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_MAX_TOOL_CALLS", "12")

    assert runtime.read_max_tool_calls() == 12


@pytest.mark.parametrize("raw", ["0", "31", "-1"])
def test_read_max_tool_calls_rejects_out_of_range(monkeypatch, raw):
    monkeypatch.setenv("RESEARCHFLOW_MAX_TOOL_CALLS", raw)

    with pytest.raises(ValueError, match="RESEARCHFLOW_MAX_TOOL_CALLS"):
        runtime.read_max_tool_calls()


def test_read_max_tool_calls_rejects_non_integer(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_MAX_TOOL_CALLS", "six")

    with pytest.raises(ValueError, match="RESEARCHFLOW_MAX_TOOL_CALLS"):
        runtime.read_max_tool_calls()


def test_create_knowledge_client_requires_backend_url(monkeypatch):
    monkeypatch.delenv("RESEARCHFLOW_BACKEND_URL", raising=False)

    with pytest.raises(ValueError, match="RESEARCHFLOW_BACKEND_URL"):
        runtime.create_knowledge_client()


class FakeChatModel(RunnableLambda):
    """Runnable that also exposes the ChatOpenAI surface runtime.py relies on."""

    def __init__(self):
        super().__init__(lambda messages: AIMessage(content="READY"))

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema):
        if schema is ResearchPlan:
            return RunnableLambda(
                lambda value: {"sub_questions": ["子问题一", "子问题二"]}
            )
        return RunnableLambda(lambda value: {"results": []})


def test_create_runtime_compiles_the_graph_registered_in_langgraph_json(monkeypatch):
    """The langgraph.json entry point must build a real, complete graph."""

    for name, value in {
        "SILICONFLOW_API_KEY": "test-key",
        "SILICONFLOW_BASE_URL": "https://example.invalid/v1",
        "SILICONFLOW_MODEL": "test-model",
        "TAVILY_API_KEY": "test-key",
        "RESEARCHFLOW_BACKEND_URL": "http://127.0.0.1:8000",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(runtime, "create_model", FakeChatModel)
    monkeypatch.setattr(runtime, "create_report_persister", lambda: None)

    graph = runtime.create_runtime()

    assert set(graph.get_graph().nodes) == {
        "__start__",
        "planner",
        "researcher",
        "execute_tool",
        "writer",
        "verifier",
        "persist",
        "__end__",
    }


def test_runtime_graph_runs_end_to_end_with_a_stubbed_model(monkeypatch):
    """Prove the real prompt chains, context schema and node wiring agree.

    Every prompt variable the runtime declares must be supplied by the graph at
    invoke time; a mismatch would only surface here.
    """

    for name, value in {
        "SILICONFLOW_API_KEY": "test-key",
        "SILICONFLOW_BASE_URL": "https://example.invalid/v1",
        "SILICONFLOW_MODEL": "test-model",
        "TAVILY_API_KEY": "test-key",
        "RESEARCHFLOW_BACKEND_URL": "http://127.0.0.1:8000",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(runtime, "create_model", FakeChatModel)

    graph = runtime.create_runtime()

    result = graph.invoke(
        {"messages": [HumanMessage(content="实验室的校准周期是什么？")]},
        context={
            "knowledge_scope": {
                "user_id": "11111111-1111-1111-1111-111111111111",
                "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            }
        },
    )

    assert result["research_query"] == "实验室的校准周期是什么？"
    assert result["sub_questions"] == ["子问题一", "子问题二"]
    assert result["report"] == "READY"
    assert result["citations"] == []
    assert result["verification"] == []
