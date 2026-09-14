from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from researchflow.backend.app import app
from researchflow.backend.database import SessionLocal
from researchflow.backend.projects import Project


client = TestClient(app)
USER_ID = uuid4()
OTHER_USER_ID = uuid4()
USER_HEADERS = {"X-ResearchFlow-User-Id": str(USER_ID)}
OTHER_USER_HEADERS = {"X-ResearchFlow-User-Id": str(OTHER_USER_ID)}


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
    create_response = client.post(
        "/projects",
        json={"name": "  Climate policy research  "},
        headers=USER_HEADERS,
    )

    assert create_response.status_code == 201
    project = create_response.json()
    assert UUID(project["project_id"])
    assert project["name"] == "Climate policy research"
    assert project["created_at"].endswith(("Z", "+00:00"))
    assert datetime_from_response(project["created_at"]).tzinfo == timezone.utc

    read_response = client.get(
        f"/projects/{project['project_id']}", headers=USER_HEADERS
    )

    assert read_response.status_code == 200
    assert read_response.json() == project
    with SessionLocal() as session:
        persisted = session.get(Project, UUID(project["project_id"]))
        assert persisted is not None
        assert persisted.owner_user_id == USER_ID


def test_duplicate_names_create_different_projects():
    first = client.post("/projects", json={"name": "Duplicate"}, headers=USER_HEADERS)
    second = client.post("/projects", json={"name": "Duplicate"}, headers=USER_HEADERS)

    assert first.status_code == second.status_code == 201
    assert first.json()["project_id"] != second.json()["project_id"]


def test_list_projects_returns_newest_first():
    assert client.get("/projects", headers=USER_HEADERS).json() == []

    projects = [
        client.post(
            "/projects", json={"name": "First"}, headers=USER_HEADERS
        ).json(),
        client.post(
            "/projects", json={"name": "Second"}, headers=USER_HEADERS
        ).json(),
    ]
    expected = sorted(
        projects,
        key=lambda project: (
            datetime_from_response(project["created_at"]),
            UUID(project["project_id"]),
        ),
        reverse=True,
    )

    response = client.get("/projects", headers=USER_HEADERS)

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
        response = client.post("/projects", json=payload, headers=USER_HEADERS)
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)


def test_invalid_uuid_returns_422():
    response = client.get("/projects/not-a-uuid", headers=USER_HEADERS)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_unknown_project_returns_404():
    response = client.get(f"/projects/{uuid4()}", headers=USER_HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_user_identity_is_required_and_validated():
    missing = client.get("/projects")
    malformed = client.get(
        "/projects", headers={"X-ResearchFlow-User-Id": "not-a-uuid"}
    )

    assert missing.status_code == 401
    assert missing.json() == {"detail": "Authentication required"}
    assert malformed.status_code == 422
    assert isinstance(malformed.json()["detail"], list)


def test_projects_are_hidden_from_other_users():
    project = client.post(
        "/projects", json={"name": "Private"}, headers=USER_HEADERS
    ).json()

    assert client.get("/projects", headers=OTHER_USER_HEADERS).json() == []
    response = client.get(
        f"/projects/{project['project_id']}", headers=OTHER_USER_HEADERS
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def datetime_from_response(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
