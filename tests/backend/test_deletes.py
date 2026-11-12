"""Deletion endpoints: projects, documents and research sessions.

These are the operations that make the evaluation repeatable: a live run creates
six Projects and thirty-six Documents, and without a delete it can never clean up
after itself.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from researchflow.backend.agent_server import get_agent_server
from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.models import Document, DocumentChunk
from researchflow.backend.projects import Project
from researchflow.backend.research_sessions import ResearchSession

client = TestClient(app)

USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}
OTHER_USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}


class FakeAgentServer:
    def __init__(self):
        self.create_calls: list[dict[str, str]] = []
        self.delete_calls: list[str] = []
        self.fail_delete = False

    def create_thread(self, *, project_id: str, research_session_id: str) -> str:
        self.create_calls.append(
            {"project_id": project_id, "research_session_id": research_session_id}
        )
        return f"thread-{len(self.create_calls)}"

    def delete_thread(self, thread_id: str) -> None:
        self.delete_calls.append(thread_id)
        if self.fail_delete:
            raise RuntimeError("agent server unavailable")


@pytest.fixture
def agent_server():
    fake = FakeAgentServer()
    app.dependency_overrides[get_agent_server] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_agent_server, None)


def create_project(headers=USER_HEADERS) -> str:
    response = client.post("/projects", json={"name": "Lifecycle"}, headers=headers)
    assert response.status_code == 201
    return response.json()["project_id"]


def add_document(project_id: str, chunks: int = 2) -> str:
    """Insert a Document and its chunks directly; upload needs live embeddings."""

    document_id = uuid4()
    with SessionLocal() as session:
        document = Document(
            document_id=document_id,
            project_id=project_id,
            filename="notes.md",
            media_type="text/markdown",
            content_text="# Notes\n\nbody",
        )
        session.add(document)
        for index in range(chunks):
            session.add(
                DocumentChunk(
                    chunk_id=uuid4(),
                    document_id=document_id,
                    chunk_index=index,
                    content=f"chunk {index}",
                    embedding=[0.01 * (index + 1)] * 1024,
                )
            )
        session.commit()
    return str(document_id)


def create_session(project_id: str, headers=USER_HEADERS) -> dict:
    response = client.post(
        f"/projects/{project_id}/research-sessions", headers=headers
    )
    assert response.status_code == 201
    return response.json()


def count(model) -> int:
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(model))


# --- document ----------------------------------------------------------------


def test_delete_document_removes_its_chunks():
    project_id = create_project()
    document_id = add_document(project_id, chunks=3)
    assert count(DocumentChunk) == 3

    response = client.delete(
        f"/projects/{project_id}/documents/{document_id}", headers=USER_HEADERS
    )

    assert response.status_code == 204
    assert response.content == b""
    assert count(Document) == 0
    assert count(DocumentChunk) == 0


def test_delete_document_of_another_project_is_not_found():
    project_id = create_project()
    other_project = create_project()
    document_id = add_document(project_id)

    response = client.delete(
        f"/projects/{other_project}/documents/{document_id}", headers=USER_HEADERS
    )

    assert response.status_code == 404
    assert count(Document) == 1


def test_delete_document_requires_the_owner():
    project_id = create_project()
    document_id = add_document(project_id)

    response = client.delete(
        f"/projects/{project_id}/documents/{document_id}", headers=OTHER_USER_HEADERS
    )

    assert response.status_code == 404
    assert count(Document) == 1


# --- research session --------------------------------------------------------


def test_delete_session_removes_the_row_and_the_thread(agent_server):
    project_id = create_project()
    created = create_session(project_id)
    thread_id = created["thread_id"]

    response = client.delete(
        f"/projects/{project_id}/research-sessions/{created['research_session_id']}",
        headers=USER_HEADERS,
    )

    assert response.status_code == 204
    assert count(ResearchSession) == 0
    assert agent_server.delete_calls == [thread_id]


def test_delete_session_still_succeeds_when_the_thread_delete_fails(agent_server):
    agent_server.fail_delete = True
    project_id = create_project()
    created = create_session(project_id)

    response = client.delete(
        f"/projects/{project_id}/research-sessions/{created['research_session_id']}",
        headers=USER_HEADERS,
    )

    assert response.status_code == 204
    assert count(ResearchSession) == 0


def test_delete_missing_session_is_not_found(agent_server):
    project_id = create_project()

    response = client.delete(
        f"/projects/{project_id}/research-sessions/{uuid4()}", headers=USER_HEADERS
    )

    assert response.status_code == 404


# --- project -----------------------------------------------------------------


def test_delete_project_removes_documents_chunks_and_sessions(agent_server):
    project_id = create_project()
    add_document(project_id, chunks=2)
    create_session(project_id)

    response = client.delete(f"/projects/{project_id}", headers=USER_HEADERS)

    assert response.status_code == 204
    assert count(Project) == 0
    assert count(Document) == 0
    assert count(DocumentChunk) == 0
    assert count(ResearchSession) == 0


def test_delete_project_is_scoped_to_the_owner():
    project_id = create_project()
    other_project = create_project()
    add_document(project_id)

    response = client.delete(f"/projects/{project_id}", headers=OTHER_USER_HEADERS)

    assert response.status_code == 404
    assert count(Project) == 2
    assert count(Document) == 1
    assert other_project


def test_delete_project_twice_returns_not_found():
    project_id = create_project()

    assert client.delete(f"/projects/{project_id}", headers=USER_HEADERS).status_code == 204
    assert client.delete(f"/projects/{project_id}", headers=USER_HEADERS).status_code == 404


def test_delete_project_leaves_other_projects_untouched():
    doomed = create_project()
    survivor = create_project()
    add_document(survivor, chunks=1)

    assert client.delete(f"/projects/{doomed}", headers=USER_HEADERS).status_code == 204

    assert count(Project) == 1
    assert count(Document) == 1
    response = client.get(f"/projects/{survivor}", headers=USER_HEADERS)
    assert response.status_code == 200
