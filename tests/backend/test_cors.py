import pytest
from fastapi.testclient import TestClient

from researchflow.backend.app import create_app


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_configured_origin_allows_json_preflight(monkeypatch, origin):
    monkeypatch.setenv(
        "RESEARCHFLOW_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )

    response = TestClient(create_app()).options(
        "/projects",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


def test_unlisted_origin_receives_no_cors_permission(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_CORS_ORIGINS", "http://localhost:3000")

    response = TestClient(create_app()).options(
        "/projects",
        headers={
            "Origin": "http://example.test",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


def test_configured_origin_allows_trusted_user_header(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_CORS_ORIGINS", "http://localhost:3000")

    response = TestClient(create_app()).options(
        "/projects",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-researchflow-user-id",
        },
    )

    assert response.status_code == 200
    assert "x-researchflow-user-id" in response.headers[
        "access-control-allow-headers"
    ].lower()
