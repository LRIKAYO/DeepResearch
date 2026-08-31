from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchflow.backend.app import app


client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_hides_database_failures(monkeypatch):
    from researchflow.backend import database
    from sqlalchemy.exc import OperationalError

    class UnavailableEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(database, "engine", UnavailableEngine())

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_create_and_read_project():
    create_response = client.post("/projects", json={"name": "  Climate policy research  "})

    assert create_response.status_code == 201
    project = create_response.json()
    assert UUID(project["project_id"])
    assert project["name"] == "Climate policy research"
    assert project["created_at"].endswith(("Z", "+00:00"))
    assert datetime_from_response(project["created_at"]).tzinfo == timezone.utc

    read_response = client.get(f"/projects/{project['project_id']}")

    assert read_response.status_code == 200
    assert read_response.json() == project


def test_duplicate_names_create_different_projects():
    first = client.post("/projects", json={"name": "Duplicate"})
    second = client.post("/projects", json={"name": "Duplicate"})

    assert first.status_code == second.status_code == 201
    assert first.json()["project_id"] != second.json()["project_id"]


def test_list_projects_returns_newest_first():
    assert client.get("/projects").json() == []

    projects = [
        client.post("/projects", json={"name": "First"}).json(),
        client.post("/projects", json={"name": "Second"}).json(),
    ]
    expected = sorted(
        projects,
        key=lambda project: (
            datetime_from_response(project["created_at"]),
            UUID(project["project_id"]),
        ),
        reverse=True,
    )

    response = client.get("/projects")

    assert response.status_code == 200
    assert response.json() == expected


def test_invalid_project_request_returns_422():
    invalid_requests = [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 121},
        {"name": 1},
        {"name": None},
        {"name": "valid", "unexpected": True},
    ]

    for payload in invalid_requests:
        response = client.post("/projects", json=payload)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)


def test_invalid_uuid_returns_422():
    response = client.get("/projects/not-a-uuid")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_unknown_project_returns_404():
    response = client.get(f"/projects/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def datetime_from_response(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
