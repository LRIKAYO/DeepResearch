"""Report persistence: the durable copy written after a run."""

from uuid import UUID, uuid4

import pytest
from langgraph.runtime import Runtime

from researchflow.agent.graph import persist
from researchflow.agent.knowledge_search import KnowledgeScope
from researchflow.agent.persistence import ReportPersister
from researchflow.agent.state import AgentContext

USER_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def context(*, with_session: bool = True) -> AgentContext:
    return AgentContext(
        knowledge_scope=KnowledgeScope(user_id=USER_ID, project_id=PROJECT_ID),
        research_session_id=SESSION_ID if with_session else None,
    )


def state() -> dict:
    return {
        "report": "# Report [c1]",
        "citations": [{"citation_id": "c1", "source_label": "ops.md"}],
        "verification": [{"citation_id": "c1", "support": "full", "reason": "ok"}],
        "tool_rounds": 2,
    }


class FakePersister:
    def __init__(self, *, report_id="r-1", raises=None):
        self.report_id = report_id
        self.raises = raises
        self.calls: list[dict] = []

    def save(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.report_id


# --- node --------------------------------------------------------------------


def test_persist_writes_the_run():
    persister = FakePersister()

    update = persist(state(), persister, Runtime(context=context()))

    assert update == {}
    assert len(persister.calls) == 1
    call = persister.calls[0]
    assert call["user_id"] == USER_ID
    assert call["project_id"] == PROJECT_ID
    assert call["research_session_id"] == SESSION_ID
    assert call["report"] == "# Report [c1]"
    assert call["citations"][0]["citation_id"] == "c1"
    assert call["verification"][0]["support"] == "full"
    assert call["tool_rounds"] == 2


def test_persist_is_skipped_without_a_session():
    persister = FakePersister()

    assert persist(state(), persister, Runtime(context=context(with_session=False))) == {}
    assert persister.calls == []


def test_persist_is_skipped_without_a_persister():
    assert persist(state(), None, Runtime(context=context())) == {}


def test_persist_is_skipped_without_a_report():
    persister = FakePersister()

    assert persist({"citations": []}, persister, Runtime(context=context())) == {}
    assert persister.calls == []


def test_persist_never_fails_the_run():
    persister = FakePersister(raises=RuntimeError("backend down"))

    assert persist(state(), persister, Runtime(context=context())) == {}


def test_persist_tolerates_a_rejected_write():
    persister = FakePersister(report_id=None)

    assert persist(state(), persister, Runtime(context=context())) == {}


def test_persist_defaults_tool_rounds_to_zero():
    persister = FakePersister()
    payload = state()
    payload.pop("tool_rounds")

    persist(payload, persister, Runtime(context=context()))

    assert persister.calls[0]["tool_rounds"] == 0


# --- client ------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_client_posts_to_the_session_reports_endpoint():
    calls: list[dict] = []

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(201, {"report_id": "r-1"})

    client = ReportPersister("http://backend.test/", post=post)

    report_id = client.save(
        user_id=USER_ID,
        project_id=PROJECT_ID,
        research_session_id=SESSION_ID,
        report="text",
        citations=[],
        verification=[],
        tool_rounds=1,
    )

    assert report_id == "r-1"
    assert calls[0]["url"] == (
        f"http://backend.test/projects/{PROJECT_ID}/research-sessions/"
        f"{SESSION_ID}/reports"
    )
    assert calls[0]["headers"] == {"X-ResearchFlow-User-Id": str(USER_ID)}
    assert calls[0]["json"] == {
        "report": "text",
        "citations": [],
        "verification": [],
        "tool_rounds": 1,
    }


@pytest.mark.parametrize(
    "response",
    [FakeResponse(503, None), FakeResponse(201, {}), FakeResponse(201, {"report_id": 5})],
)
def test_client_returns_none_when_the_write_is_not_accepted(response):
    client = ReportPersister("http://backend.test", post=lambda *a, **k: response)

    assert (
        client.save(
            user_id=USER_ID,
            project_id=PROJECT_ID,
            research_session_id=SESSION_ID,
            report="text",
            citations=[],
            verification=[],
            tool_rounds=0,
        )
        is None
    )


def test_client_rejects_an_empty_base_url():
    with pytest.raises(ValueError):
        ReportPersister("   ")
