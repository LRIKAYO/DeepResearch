from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from researchflow.backend import documents as documents_module
from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.knowledge_dependencies import get_embedding_factory
from researchflow.backend.models import Document, DocumentChunk


client = TestClient(app)
USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}
OTHER_USER_HEADERS = {"X-ResearchFlow-User-Id": str(uuid4())}


class FakeEmbeddings:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.document_calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(texts)
        if self.error:
            raise self.error
        return [[1.0, *([0.0] * 1023)] for _ in texts]


@pytest.fixture
def fake_embeddings():
    fake = FakeEmbeddings()
    app.dependency_overrides[get_embedding_factory] = lambda: lambda: fake
    yield fake
    app.dependency_overrides.pop(get_embedding_factory, None)


def create_project(headers=USER_HEADERS) -> str:
    response = client.post("/projects", json={"name": "Knowledge"}, headers=headers)
    assert response.status_code == 201
    return response.json()["project_id"]


def row_counts() -> tuple[int, int]:
    with SessionLocal() as session:
        return (
            session.scalar(select(func.count()).select_from(Document)),
            session.scalar(select(func.count()).select_from(DocumentChunk)),
        )


def test_upload_read_and_list_markdown(fake_embeddings):
    project_id = create_project()
    source = "# Target\n\nThe policy sets a 2030 emissions target."

    response = client.post(
        f"/projects/{project_id}/documents",
        headers=USER_HEADERS,
        files={"file": ("  policy.md  ", source.encode(), "text/markdown")},
    )

    assert response.status_code == 201
    document = response.json()
    assert UUID(document["document_id"])
    assert document["project_id"] == project_id
    assert document["filename"] == "policy.md"
    assert document["media_type"] == "text/markdown"
    assert "content_text" not in document
    assert fake_embeddings.document_calls == [[source]]
    assert row_counts() == (1, 1)

    assert client.get(
        f"/projects/{project_id}/documents/{document['document_id']}",
        headers=USER_HEADERS,
    ).json() == document
    assert client.get(
        f"/projects/{project_id}/documents", headers=USER_HEADERS
    ).json() == [document]


@pytest.mark.parametrize(
    ("filename", "content", "media_type", "status_code", "detail"),
    [
        ("notes.txt", b"content", "text/markdown", 422, "Invalid Markdown filename"),
        ("notes.md", b"content", "text/plain", 415, "Only text/markdown is supported"),
        ("notes.md", b"   \n", "text/markdown", 422, "Markdown document cannot be empty"),
        ("notes.md", b"\xff", "text/markdown", 422, "Markdown document must be UTF-8"),
        (
            "notes.md",
            b"x" * 1_048_577,
            "text/markdown",
            413,
            "Markdown document exceeds the 1048576-byte limit",
        ),
    ],
    ids=["filename", "media-type", "empty", "utf8", "size"],
)
def test_upload_rejects_invalid_files_without_embedding(
    fake_embeddings, filename, content, media_type, status_code, detail
):
    project_id = create_project()

    response = client.post(
        f"/projects/{project_id}/documents",
        headers=USER_HEADERS,
        files={"file": (filename, content, media_type)},
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert fake_embeddings.document_calls == []
    assert row_counts() == (0, 0)


@pytest.mark.parametrize(
    "files",
    [
        {},
        [
            ("file", ("notes.md", b"content", "text/markdown")),
            ("extra", (None, "unexpected")),
        ],
    ],
)
def test_upload_rejects_missing_or_extra_parts_without_embedding(
    fake_embeddings, files
):
    project_id = create_project()

    response = client.post(
        f"/projects/{project_id}/documents", headers=USER_HEADERS, files=files
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert fake_embeddings.document_calls == []
    assert row_counts() == (0, 0)


def test_upload_embedding_failure_is_atomic_and_sanitized():
    fake = FakeEmbeddings(error=RuntimeError("provider secret"))
    app.dependency_overrides[get_embedding_factory] = lambda: lambda: fake
    project_id = create_project()

    try:
        response = client.post(
            f"/projects/{project_id}/documents",
            headers=USER_HEADERS,
            files={"file": ("notes.md", b"content", "text/markdown")},
        )
    finally:
        app.dependency_overrides.pop(get_embedding_factory, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Knowledge indexing unavailable"}
    assert row_counts() == (0, 0)


def test_other_user_project_is_hidden_before_embedding(fake_embeddings):
    project_id = create_project()

    response = client.post(
        f"/projects/{project_id}/documents",
        headers=OTHER_USER_HEADERS,
        files={"file": ("notes.md", b"content", "text/markdown")},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}
    assert fake_embeddings.document_calls == []
    assert row_counts() == (0, 0)


def test_unknown_project_is_rejected_before_embedding(fake_embeddings):
    response = client.post(
        f"/projects/{uuid4()}/documents",
        headers=USER_HEADERS,
        files={"file": ("notes.md", b"content", "text/markdown")},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}
    assert fake_embeddings.document_calls == []
    assert row_counts() == (0, 0)


def test_document_read_and_list_hide_other_user(fake_embeddings):
    project_id = create_project()
    created = client.post(
        f"/projects/{project_id}/documents",
        headers=USER_HEADERS,
        files={"file": ("notes.md", b"content", "text/markdown")},
    ).json()

    assert client.get(
        f"/projects/{project_id}/documents", headers=OTHER_USER_HEADERS
    ).json() == {"detail": "Project not found"}
    assert client.get(
        f"/projects/{project_id}/documents/{created['document_id']}",
        headers=OTHER_USER_HEADERS,
    ).json() == {"detail": "Project not found"}


def test_document_read_does_not_cross_project(fake_embeddings):
    project_id = create_project()
    other_project_id = create_project()
    created = client.post(
        f"/projects/{project_id}/documents",
        headers=USER_HEADERS,
        files={"file": ("notes.md", b"content", "text/markdown")},
    ).json()

    response = client.get(
        f"/projects/{other_project_id}/documents/{created['document_id']}",
        headers=USER_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found"}


def test_zero_norm_vector_is_atomic_and_sanitized():
    fake = FakeEmbeddings()

    fake.embed_documents = lambda texts: [[0.0] * 1024 for _ in texts]
    app.dependency_overrides[get_embedding_factory] = lambda: lambda: fake
    project_id = create_project()

    try:
        response = client.post(
            f"/projects/{project_id}/documents",
            headers=USER_HEADERS,
            files={"file": ("notes.md", b"content", "text/markdown")},
        )
    finally:
        app.dependency_overrides.pop(get_embedding_factory, None)

    assert response.status_code == 503
    assert response.json() == {"detail": "Knowledge indexing unavailable"}
    assert row_counts() == (0, 0)


def test_chunking_failure_is_atomic_and_sanitized(fake_embeddings, monkeypatch):
    project_id = create_project()

    def fail_chunking(content: str):
        raise RuntimeError("chunking detail")

    monkeypatch.setattr(documents_module, "chunk_markdown", fail_chunking)
    response = client.post(
        f"/projects/{project_id}/documents",
        headers=USER_HEADERS,
        files={"file": ("notes.md", b"content", "text/markdown")},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Knowledge indexing unavailable"}
    assert fake_embeddings.document_calls == []
    assert row_counts() == (0, 0)


def test_commit_failure_is_atomic_and_sanitized(fake_embeddings, monkeypatch):
    project_id = create_project()

    def fail_commit(self):
        raise RuntimeError("database detail")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post(
        f"/projects/{project_id}/documents",
        headers=USER_HEADERS,
        files={"file": ("notes.md", b"content", "text/markdown")},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Knowledge indexing unavailable"}
    assert row_counts() == (0, 0)
