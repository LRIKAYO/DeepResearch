import pytest

from researchflow.agent import runtime


def test_create_runtime_rejects_missing_model_key(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    with pytest.raises(ValueError, match="SILICONFLOW_API_KEY"):
        runtime.create_runtime()


def test_create_runtime_wires_one_model_to_graph(monkeypatch):
    model = object()
    tool = object()
    writer = object()
    graph = object()
    captured = {}

    monkeypatch.setattr(runtime, "create_model", lambda: model)
    monkeypatch.setattr(runtime, "create_web_search", lambda: tool)
    monkeypatch.setattr(runtime, "create_writer", lambda received: writer)

    def fake_build_graph(*, researcher_model, tool, writer_impl):
        captured.update(
            researcher_model=researcher_model,
            tool=tool,
            writer_impl=writer_impl,
        )
        return graph

    monkeypatch.setattr(runtime, "build_graph", fake_build_graph)

    assert runtime.create_runtime() is graph
    assert captured == {
        "researcher_model": model,
        "tool": tool,
        "writer_impl": writer,
    }
