from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from researchflow.backend.agent_server import AgentServerClient, get_agent_server
from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.research_sessions import ResearchSession, create_research_session


client = TestClient(app)
USER_ID = uuid4()
OTHER_USER_ID = uuid4()
USER_HEADERS = {"X-ResearchFlow-User-Id": str(USER_ID)}
OTHER_USER_HEADERS = {"X-ResearchFlow-User-Id": str(OTHER_USER_ID)}


class FakeAgentServer:
    def __init__(self):
        self.create_calls: list[dict[str, str]] = []
        self.delete_calls: list[str] = []
        self.unavailable = False

    def create_thread(self, *, project_id: str, research_session_id: str) -> str:
        self.create_calls.append(
            {
                "project_id": project_id,
                "research_session_id": research_session_id,
            }
        )
        if self.unavailable:
            raise RuntimeError("agent failed")
        return f"thread-{len(self.create_calls)}"

    def delete_thread(self, thread_id: str) -> None:
        self.delete_calls.append(thread_id)


@pytest.fixture
def fake_agent_server():
    agent_server = FakeAgentServer()
    app.dependency_overrides[get_agent_server] = lambda: agent_server
    yield agent_server
    app.dependency_overrides.pop(get_agent_server, None)


def create_project(name: str, headers: dict[str, str] = USER_HEADERS) -> dict:
    response = client.post("/projects", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_create_read_and_list_research_sessions(fake_agent_server):
    project = create_project("Climate")
    other_project = create_project("Other")
    assert (
        client.get(
            f"/projects/{project['project_id']}/research-sessions",
            headers=USER_HEADERS,
        ).json()
        == []
    )

    sessions = []
    for _ in range(2):
        response = client.post(
            f"/projects/{project['project_id']}/research-sessions",
            headers=USER_HEADERS,
        )
        assert response.status_code == 201
        sessions.append(response.json())

    first_session = sessions[0]
    assert UUID(first_session["research_session_id"])
    assert first_session["project_id"] == project["project_id"]
    assert first_session["thread_id"] == "thread-1"
    assert (
        datetime.fromisoformat(first_session["created_at"].replace("Z", "+00:00")).tzinfo
        == timezone.utc
    )
    assert fake_agent_server.create_calls[0] == {
        "project_id": project["project_id"],
        "research_session_id": first_session["research_session_id"],
    }

    with SessionLocal() as db:
        persisted = db.get(ResearchSession, UUID(first_session["research_session_id"]))
        assert persisted is not None
        assert str(persisted.project_id) == project["project_id"]
        assert persisted.thread_id == first_session["thread_id"]

    expected = sorted(
        sessions,
        key=lambda research_session: (
            datetime.fromisoformat(research_session["created_at"].replace("Z", "+00:00")),
            UUID(research_session["research_session_id"]),
        ),
        reverse=True,
    )
    list_response = client.get(
        f"/projects/{project['project_id']}/research-sessions",
        headers=USER_HEADERS,
    )
    assert list_response.status_code == 200
    assert list_response.json() == expected

    read_response = client.get(
        f"/projects/{project['project_id']}/research-sessions/"
        f"{first_session['research_session_id']}",
        headers=USER_HEADERS,
    )
    assert read_response.status_code == 200
    assert read_response.json() == first_session

    wrong_project = client.get(
        f"/projects/{other_project['project_id']}/research-sessions/"
        f"{first_session['research_session_id']}",
        headers=USER_HEADERS,
    )
    assert wrong_project.status_code == 404
    assert wrong_project.json() == {"detail": "Research session not found"}


def test_missing_project_does_not_call_agent(fake_agent_server):
    project_id = uuid4()

    response = client.post(
        f"/projects/{project_id}/research-sessions", headers=USER_HEADERS
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}
    assert fake_agent_server.create_calls == []


def test_unknown_project_is_rejected_before_session_lookup(fake_agent_server):
    project_id = uuid4()
    research_session_id = uuid4()

    list_response = client.get(
        f"/projects/{project_id}/research-sessions", headers=USER_HEADERS
    )
    read_response = client.get(
        f"/projects/{project_id}/research-sessions/{research_session_id}",
        headers=USER_HEADERS,
    )

    assert list_response.status_code == read_response.status_code == 404
    assert list_response.json() == read_response.json() == {"detail": "Project not found"}


def test_agent_unavailable_returns_503_and_creates_no_row(fake_agent_server):
    project = create_project("Unavailable Agent")
    fake_agent_server.unavailable = True

    response = client.post(
        f"/projects/{project['project_id']}/research-sessions",
        headers=USER_HEADERS,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Agent service unavailable"}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ResearchSession)) == 0


def test_database_failure_attempts_one_thread_delete():
    project_id = uuid4()
    db = MagicMock(spec=Session)
    db.scalar.return_value = object()
    db.commit.side_effect = RuntimeError("database failed")
    agent_server = MagicMock(spec=AgentServerClient)
    agent_server.create_thread.return_value = "thread-1"

    with pytest.raises(RuntimeError, match="database failed"):
        create_research_session(
            db=db,
            agent_server=agent_server,
            project_id=project_id,
            owner_user_id=USER_ID,
        )

    agent_server.delete_thread.assert_called_once_with("thread-1")


def test_other_user_cannot_access_project_sessions(fake_agent_server):
    project = create_project("Private sessions")
    created = client.post(
        f"/projects/{project['project_id']}/research-sessions",
        headers=USER_HEADERS,
    ).json()
    fake_agent_server.create_calls.clear()

    create_response = client.post(
        f"/projects/{project['project_id']}/research-sessions",
        headers=OTHER_USER_HEADERS,
    )
    list_response = client.get(
        f"/projects/{project['project_id']}/research-sessions",
        headers=OTHER_USER_HEADERS,
    )
    read_response = client.get(
        f"/projects/{project['project_id']}/research-sessions/"
        f"{created['research_session_id']}",
        headers=OTHER_USER_HEADERS,
    )

    assert create_response.status_code == 404
    assert list_response.status_code == 404
    assert read_response.status_code == 404
    assert create_response.json() == {"detail": "Project not found"}
    assert list_response.json() == {"detail": "Project not found"}
    assert read_response.json() == {"detail": "Project not found"}
    assert fake_agent_server.create_calls == []
