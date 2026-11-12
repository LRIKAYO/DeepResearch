"""Chunk context: the window the Agent uses to widen a retrieval hit."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.models import Document, DocumentChunk

client = TestClient(app)

USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}
OTHER_USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}


def make_project(headers=USER_HEADERS) -> str:
    response = client.post("/projects", json={"name": "Context"}, headers=headers)
    assert response.status_code == 201
    return response.json()["project_id"]


def add_document(project_id: str, chunks: int = 6) -> tuple[str, list[str]]:
    document_id = uuid4()
    chunk_ids: list[str] = []
    with SessionLocal() as session:
        session.add(
            Document(
                document_id=document_id,
                project_id=project_id,
                filename="notes.md",
                media_type="text/markdown",
                content_text="# Notes",
            )
        )
        for index in range(chunks):
            chunk_id = uuid4()
            chunk_ids.append(str(chunk_id))
            session.add(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    chunk_index=index,
                    content=f"chunk-{index} body",
                    embedding=[0.01] * 1024,
                )
            )
        session.commit()
    return str(document_id), chunk_ids


def context_url(project_id: str, chunk_id: str) -> str:
    return f"/projects/{project_id}/knowledge/chunks/{chunk_id}/context"


def test_default_window_includes_two_neighbours():
    project_id = make_project()
    _, chunk_ids = add_document(project_id, chunks=6)

    response = client.get(context_url(project_id, chunk_ids[3]), headers=USER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["chunk_index"] == 3
    assert body["start_index"] == 1
    assert body["end_index"] == 5
    for index in range(1, 6):
        assert f"chunk-{index} body" in body["content"]
    assert "chunk-0 body" not in body["content"]


def test_window_is_clamped_at_the_document_start():
    project_id = make_project()
    _, chunk_ids = add_document(project_id, chunks=4)

    body = client.get(
        context_url(project_id, chunk_ids[0]), headers=USER_HEADERS
    ).json()

    assert body["start_index"] == 0
    assert body["end_index"] == 2


def test_window_is_clamped_at_the_document_end():
    project_id = make_project()
    _, chunk_ids = add_document(project_id, chunks=4)

    body = client.get(
        context_url(project_id, chunk_ids[3]), headers=USER_HEADERS
    ).json()

    assert body["end_index"] == 3


def test_radius_zero_returns_only_the_chunk():
    project_id = make_project()
    _, chunk_ids = add_document(project_id, chunks=4)

    body = client.get(
        f"{context_url(project_id, chunk_ids[2])}?radius=0", headers=USER_HEADERS
    ).json()

    assert body["content"] == "chunk-2 body"
    assert body["start_index"] == body["end_index"] == 2


@pytest.mark.parametrize("radius", [4, -1])
def test_radius_is_bounded(radius):
    project_id = make_project()
    _, chunk_ids = add_document(project_id, chunks=4)

    response = client.get(
        f"{context_url(project_id, chunk_ids[1])}?radius={radius}", headers=USER_HEADERS
    )

    assert response.status_code == 422


def test_unknown_chunk_is_not_found():
    project_id = make_project()

    response = client.get(context_url(project_id, str(uuid4())), headers=USER_HEADERS)

    assert response.status_code == 404


def test_chunk_of_another_project_is_not_found():
    project_id = make_project()
    other_project = make_project()
    _, chunk_ids = add_document(project_id)

    response = client.get(context_url(other_project, chunk_ids[1]), headers=USER_HEADERS)

    assert response.status_code == 404


def test_another_user_cannot_read_the_window():
    project_id = make_project()
    _, chunk_ids = add_document(project_id)

    response = client.get(context_url(project_id, chunk_ids[1]), headers=OTHER_USER_HEADERS)

    assert response.status_code == 404


def test_missing_identity_is_unauthorized():
    project_id = make_project()
    _, chunk_ids = add_document(project_id)

    response = client.get(context_url(project_id, chunk_ids[1]))

    assert response.status_code == 401

def test_the_matched_chunk_comes_first():
    """The excerpt and the verifier read a prefix, so the match must lead."""

    project_id = make_project()
    _, chunk_ids = add_document(project_id, chunks=6)

    body = client.get(context_url(project_id, chunk_ids[3]), headers=USER_HEADERS).json()

    order = [
        line for line in body["content"].split("\n\n") if line.startswith("chunk-")
    ]
    assert order == [
        "chunk-3 body",
        "chunk-4 body",
        "chunk-5 body",
        "chunk-1 body",
        "chunk-2 body",
    ]
    assert body["content"].startswith("chunk-3 body")
