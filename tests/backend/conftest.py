import os
from urllib.parse import urlparse

import pytest


def test_database_url() -> str:
    test_url = os.getenv("RESEARCHFLOW_TEST_DATABASE_URL")
    runtime_url = os.getenv("RESEARCHFLOW_DATABASE_URL")
    if not test_url:
        pytest.exit("RESEARCHFLOW_TEST_DATABASE_URL is required for Backend tests")
    if test_url == runtime_url:
        pytest.exit("test and runtime database URLs must differ")
    if urlparse(test_url).path.rstrip("/") != "/researchflow_test":
        pytest.exit("Backend tests may only clean the researchflow_test database")
    return test_url


TEST_DATABASE_URL = test_database_url()
os.environ["RESEARCHFLOW_DATABASE_URL"] = TEST_DATABASE_URL


@pytest.fixture(autouse=True)
def clean_backend_tables():
    from sqlalchemy import text

    from researchflow.backend.database import engine

    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE reports, document_chunks, documents, "
                "research_sessions, projects"
            )
        )
