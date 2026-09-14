from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.knowledge_dependencies import get_embedding_factory
from researchflow.backend.models import Document, DocumentChunk
from researchflow.backend.projects import Project


client = TestClient(app)
USER_ID = uuid4()
OTHER_USER_ID = uuid4()
USER_HEADERS = {"X-ResearchFlow-User-Id": str(USER_ID)}
OTHER_USER_HEADERS = {"X-ResearchFlow-User-Id": str(OTHER_USER_ID)}
QUERY_VECTOR = [1.0, *([0.0] * 1023)]


class FakeEmbeddings:
    def __init__(self, query_vector=QUERY_VECTOR):
        self.query_vector = query_vector
        self.queries: list[str] = []

    def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return self.query_vector


@pytest.fixture
def fake_embeddings():
    fake = FakeEmbeddings()
    app.dependency_overrides[get_embedding_factory] = lambda: lambda: fake
    yield fake
    app.dependency_overrides.pop(get_embedding_factory, None)


def add_project(owner_user_id=USER_ID) -> UUID:
    project_id = uuid4()
    with SessionLocal.begin() as session:
        session.add(
            Project(
                project_id=project_id,
                owner_user_id=owner_user_id,
                name="Knowledge",
            )
        )
    return project_id


def add_chunk(
    project_id: UUID,
    *,
    chunk_id: UUID | None = None,
    vector: list[float] = QUERY_VECTOR,
    filename: str = "source.md",
    content: str = "evidence",
) -> UUID:
    document_id = uuid4()
    chunk_id = chunk_id or uuid4()
    with SessionLocal.begin() as session:
        session.add(
            Document(
                document_id=document_id,
                project_id=project_id,
                filename=filename,
                media_type="text/markdown",
                content_text=content,
            )
        )
        session.add(
            DocumentChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                chunk_index=0,
                content=content,
                embedding=vector,
            )
        )
    return chunk_id


def search(project_id: UUID, *, headers=USER_HEADERS, limit=5):
    return client.post(
        f"/projects/{project_id}/knowledge/search",
        headers=headers,
        json={"query": "  emissions target  ", "limit": limit},
    )


def test_search_returns_typed_hit_and_trims_query(fake_embeddings):
    project_id = add_project()
    chunk_id = add_chunk(
        project_id, filename="policy.md", content="The 2030 target is binding."
    )

    response = search(project_id)

    assert response.status_code == 200
    assert response.json() == [
        {
            "document_id": response.json()[0]["document_id"],
            "chunk_id": str(chunk_id),
            "filename": "policy.md",
            "content": "The 2030 target is binding.",
            "score": pytest.approx(1.0),
        }
    ]
    assert UUID(response.json()[0]["document_id"])
    assert fake_embeddings.queries == ["emissions target"]


def test_search_filters_project_and_owner_before_limit(fake_embeddings):
    target_project = add_project()
    other_project = add_project()
    other_user_project = add_project(OTHER_USER_ID)
    target_chunk = add_chunk(
        target_project,
        vector=[0.8, 0.6, *([0.0] * 1022)],
        content="eligible",
    )
    add_chunk(other_project, content="closer other project")
    add_chunk(other_user_project, content="closer other user")

    response = search(target_project, limit=1)

    assert response.status_code == 200
    assert [hit["chunk_id"] for hit in response.json()] == [str(target_chunk)]

    hidden = search(other_user_project, headers=USER_HEADERS)
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "Project not found"}
    assert fake_embeddings.queries == ["emissions target"]


def test_search_empty_project_returns_empty_list(fake_embeddings):
    project_id = add_project()

    response = search(project_id)

    assert response.status_code == 200
    assert response.json() == []


def test_search_limit_and_chunk_id_tie_break(fake_embeddings):
    project_id = add_project()
    later = UUID(int=2)
    earlier = UUID(int=1)
    add_chunk(project_id, chunk_id=later, content="later UUID")
    add_chunk(project_id, chunk_id=earlier, content="earlier UUID")

    response = search(project_id, limit=1)

    assert response.status_code == 200
    assert [hit["chunk_id"] for hit in response.json()] == [str(earlier)]


def test_search_vector_validation_failure_is_sanitized_before_sql():
    project_id = add_project()
    add_chunk(project_id)
    fake = FakeEmbeddings(query_vector=[1.0])
    app.dependency_overrides[get_embedding_factory] = lambda: lambda: fake

    try:
        response = search(project_id)
    finally:
        app.dependency_overrides.pop(get_embedding_factory, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Knowledge search unavailable"}
    assert fake.queries == ["emissions target"]
