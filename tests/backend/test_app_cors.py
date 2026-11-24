"""CORS preflight tests for the ResearchFlow backend application."""

import os

from fastapi.testclient import TestClient


def _ensure_database_url(monkeypatch) -> None:
    if not os.getenv("RESEARCHFLOW_DATABASE_URL"):
        monkeypatch.setenv(
            "RESEARCHFLOW_DATABASE_URL",
            os.getenv(
                "RESEARCHFLOW_TEST_DATABASE_URL",
                "postgresql+psycopg://test:test@localhost:5432/researchflow_test",
            ),
        )


def test_cors_allows_delete_preflight_for_document_deletion(monkeypatch):
    _ensure_database_url(monkeypatch)
    monkeypatch.setenv("RESEARCHFLOW_CORS_ORIGINS", "http://localhost:3000")

    from researchflow.backend.app import create_app

    client = TestClient(create_app())
    response = client.options(
        "/projects/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/documents/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "X-ResearchFlow-User-Id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    allowed_methods = {
        method.strip().upper()
        for method in response.headers["access-control-allow-methods"].split(",")
    }
    assert {"GET", "POST", "DELETE"} <= allowed_methods


def test_cors_is_disabled_when_origins_env_is_unset(monkeypatch):
    _ensure_database_url(monkeypatch)
    monkeypatch.delenv("RESEARCHFLOW_CORS_ORIGINS", raising=False)

    from researchflow.backend.app import create_app

    client = TestClient(create_app())
    response = client.options(
        "/projects/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/documents/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
        },
    )

    assert "access-control-allow-origin" not in response.headers
