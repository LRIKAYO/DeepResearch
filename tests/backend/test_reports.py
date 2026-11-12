"""Persisted Reports: the durable copy of what the Agent produced."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from researchflow.backend.agent_server import get_agent_server
from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.reports import MAX_REPORT_CHARS, Report

client = TestClient(app)

USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}
OTHER_USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}


class FakeAgentServer:
    def __init__(self):
        self.created = 0
        self.deleted: list[str] = []

    def create_thread(self, *, project_id: str, research_session_id: str) -> str:
        self.created += 1
        return f"thread-{self.created}"

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


@pytest.fixture
def agent_server():
    fake = FakeAgentServer()
    app.dependency_overrides[get_agent_server] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_agent_server, None)


def make_project(headers=USER_HEADERS) -> str:
    project = client.post("/projects", json={"name": "Reports"}, headers=headers)
    assert project.status_code == 201
    return project.json()["project_id"]


def add_session(project_id: str, headers=USER_HEADERS) -> str:
    session = client.post(
        f"/projects/{project_id}/research-sessions", headers=headers
    )
    assert session.status_code == 201
    return session.json()["research_session_id"]


def make_session(agent_server, headers=USER_HEADERS) -> tuple[str, str]:
    project_id = make_project(headers)
    return project_id, add_session(project_id, headers)


def payload(**overrides):
    body = {
        "report": "# Report\n\nCalibration defaults to 3 [c1].",
        "citations": [
            {
                "citation_id": "c1",
                "source_type": "user_upload",
                "source_label": "ops.md",
                "excerpt": "defaults to 3",
                "provenance": {"filename": "ops.md"},
            }
        ],
        "verification": [{"citation_id": "c1", "support": "full", "reason": "matches"}],
        "tool_rounds": 2,
    }
    body.update(overrides)
    return body


def count_reports() -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Report))


def test_create_report_echoes_what_was_stored(agent_server):
    project_id, session_id = make_session(agent_server)

    response = client.post(
        f"/projects/{project_id}/research-sessions/{session_id}/reports",
        json=payload(),
        headers=USER_HEADERS,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["report"].startswith("# Report")
    assert body["citations"][0]["citation_id"] == "c1"
    assert body["verification"][0]["support"] == "full"
    assert body["tool_rounds"] == 2
    assert body["created_at"].endswith(("Z", "+00:00"))
    assert body["research_session_id"] == session_id


def test_reports_are_append_only_and_listed_newest_first(agent_server):
    project_id, session_id = make_session(agent_server)
    url = f"/projects/{project_id}/research-sessions/{session_id}/reports"

    first = client.post(url, json=payload(report="first [c1]"), headers=USER_HEADERS)
    second = client.post(url, json=payload(report="second [c1]"), headers=USER_HEADERS)

    assert first.status_code == 201 and second.status_code == 201
    assert count_reports() == 2

    listed = client.get(url, headers=USER_HEADERS)
    assert listed.status_code == 200
    reports = [item["report"] for item in listed.json()]
    assert reports == ["second [c1]", "first [c1]"]


def test_read_one_report(agent_server):
    project_id, session_id = make_session(agent_server)
    base = f"/projects/{project_id}/research-sessions/{session_id}/reports"
    created = client.post(base, json=payload(), headers=USER_HEADERS).json()

    response = client.get(f"{base}/{created['report_id']}", headers=USER_HEADERS)

    assert response.status_code == 200
    assert response.json()["report"] == created["report"]


def test_unknown_report_is_not_found(agent_server):
    project_id, session_id = make_session(agent_server)

    response = client.get(
        f"/projects/{project_id}/research-sessions/{session_id}/reports/{uuid4()}",
        headers=USER_HEADERS,
    )

    assert response.status_code == 404


def test_a_report_belongs_to_one_session(agent_server):
    project_id = make_project()
    first_session = add_session(project_id)
    second_session = add_session(project_id)
    base = f"/projects/{project_id}/research-sessions/{first_session}/reports"
    client.post(base, json=payload(), headers=USER_HEADERS)

    other = client.get(
        f"/projects/{project_id}/research-sessions/{second_session}/reports",
        headers=USER_HEADERS,
    )

    assert other.status_code == 200
    assert other.json() == []


def test_unknown_session_is_not_found(agent_server):
    project_id, _ = make_session(agent_server)

    response = client.post(
        f"/projects/{project_id}/research-sessions/{uuid4()}/reports",
        json=payload(),
        headers=USER_HEADERS,
    )

    assert response.status_code == 404


def test_another_user_cannot_write_or_read_reports(agent_server):
    project_id, session_id = make_session(agent_server)
    base = f"/projects/{project_id}/research-sessions/{session_id}/reports"

    assert (
        client.post(base, json=payload(), headers=OTHER_USER_HEADERS).status_code == 404
    )
    assert client.get(base, headers=OTHER_USER_HEADERS).status_code == 404
    assert count_reports() == 0


@pytest.mark.parametrize(
    "body",
    [
        payload(report=""),
        payload(report="   "),
        payload(report="x" * (MAX_REPORT_CHARS + 1)),
        payload(tool_rounds=-1),
        payload(tool_rounds=101),
        payload(unexpected="field"),
    ],
)
def test_invalid_payloads_are_rejected(agent_server, body):
    project_id, session_id = make_session(agent_server)

    response = client.post(
        f"/projects/{project_id}/research-sessions/{session_id}/reports",
        json=body,
        headers=USER_HEADERS,
    )

    assert response.status_code == 422
    assert count_reports() == 0


def test_missing_identity_is_unauthorized(agent_server):
    project_id, session_id = make_session(agent_server)

    response = client.post(
        f"/projects/{project_id}/research-sessions/{session_id}/reports",
        json=payload(),
    )

    assert response.status_code == 401


def test_deleting_the_session_deletes_its_reports(agent_server):
    project_id, session_id = make_session(agent_server)
    base = f"/projects/{project_id}/research-sessions/{session_id}/reports"
    client.post(base, json=payload(), headers=USER_HEADERS)
    assert count_reports() == 1

    response = client.delete(
        f"/projects/{project_id}/research-sessions/{session_id}", headers=USER_HEADERS
    )

    assert response.status_code == 204
    assert count_reports() == 0


def test_deleting_the_project_deletes_its_reports(agent_server):
    project_id, session_id = make_session(agent_server)
    client.post(
        f"/projects/{project_id}/research-sessions/{session_id}/reports",
        json=payload(),
        headers=USER_HEADERS,
    )

    response = client.delete(f"/projects/{project_id}", headers=USER_HEADERS)

    assert response.status_code == 204
    assert count_reports() == 0
