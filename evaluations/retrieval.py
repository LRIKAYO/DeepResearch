"""P7-003C: logical ground truth and the real scoped API Recall@5 baseline.

Run as a fresh process with ``python -m evaluations.retrieval``. Importing this
module for arithmetic/validator tests never imports the Backend or connects to DB.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.engine import make_url

from researchflow.knowledge.chunking import chunk_markdown


K = 5
DEFAULT_FIXTURE = Path(__file__).with_name("retrieval_v1.json")


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Passage(FixtureModel):
    document_key: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)


class FixtureDocument(FixtureModel):
    document_key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00]+\.md$")
    content: str = Field(min_length=1)


class FixtureProject(FixtureModel):
    project_key: str = Field(min_length=1)
    documents: list[FixtureDocument] = Field(min_length=1)


class RetrievalCase(FixtureModel):
    case_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=2000)
    relevant_passages: list[Passage] = Field(min_length=1, max_length=K)
    rationale: str = Field(min_length=1)


class RetrievalFixture(FixtureModel):
    schema_version: Literal[1]
    dataset_version: str = Field(min_length=1)
    label_review: Literal["synthetic_ai_reviewed"]
    label_note: str = Field(min_length=1)
    projects: list[FixtureProject] = Field(min_length=1)
    cases: list[RetrievalCase] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_references(self):
        _unique([project.project_key for project in self.projects], "project_key")
        _unique([case.case_id for case in self.cases], "case_id")
        chunks = {}
        candidate_counts = {}
        for project in self.projects:
            _unique([doc.document_key for doc in project.documents], "document_key")
            candidate_counts[project.project_key] = 0
            for document in project.documents:
                count = len(chunk_markdown(document.content))
                if count == 0:
                    raise ValueError("Every Document must contain a passage")
                chunks[project.project_key, document.document_key] = count
                candidate_counts[project.project_key] += count
        if len(chunks) < 2:
            raise ValueError("The baseline requires at least two Documents")
        if not any(len(case.relevant_passages) > 1 for case in self.cases):
            raise ValueError("The baseline requires a multi-relevant case")
        for case in self.cases:
            if candidate_counts.get(case.project_key, 0) <= K:
                raise ValueError("Each evaluated Project must contain more than K passages")
            _unique(
                [(p.document_key, p.chunk_index) for p in case.relevant_passages],
                "relevant passage",
            )
            for passage in case.relevant_passages:
                count = chunks.get((case.project_key, passage.document_key), 0)
                if passage.chunk_index >= count:
                    raise ValueError("Relevant passage references a missing Document/chunk")
        return self


def _unique(values, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


def load_fixture(path: Path = DEFAULT_FIXTURE) -> tuple[RetrievalFixture, str]:
    raw = path.read_bytes()
    return RetrievalFixture.model_validate_json(raw), hashlib.sha256(raw).hexdigest()


def resolve_relevant(
    case: RetrievalCase, runtime_chunks: dict[tuple[str, str, int], str]
) -> set[str]:
    """Resolve logical references against this ingestion only, never persisted IDs."""
    try:
        result = {
            runtime_chunks[case.project_key, passage.document_key, passage.chunk_index]
            for passage in case.relevant_passages
        }
    except KeyError:
        raise ValueError("Unresolved ground-truth passage") from None
    if len(result) != len(case.relevant_passages) or not all(result):
        raise ValueError("Runtime chunk IDs must be non-empty and distinct")
    return result


def recall_at_k(relevant: set[str], ranked: list[str], k: int = K) -> float:
    if not relevant or type(k) is not int or k < 1:
        raise ValueError("Recall requires non-empty ground truth and positive integer K")
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def macro_recall(values: list[float]) -> float:
    if not values or any(not 0 <= value <= 1 for value in values):
        raise ValueError("Macro recall requires non-empty values in [0, 1]")
    return sum(values) / len(values)


def require_test_database(database_url: str | None) -> str:
    """No Backend import or connection may precede this guard."""
    try:
        url = make_url(database_url or "")
    except Exception:
        raise ValueError("RESEARCHFLOW_TEST_DATABASE_URL must be a valid test URL") from None
    if (
        url.drivername != "postgresql+psycopg"
        or url.database != "researchflow_test"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.query
    ):
        raise ValueError("Baseline permits only local researchflow_test without URL options")
    return database_url


def run_baseline(fixture_path: Path = DEFAULT_FIXTURE) -> dict:
    fixture, fixture_hash = load_fixture(fixture_path)
    test_url = require_test_database(os.getenv("RESEARCHFLOW_TEST_DATABASE_URL"))
    if any(name.startswith("researchflow.backend.") for name in sys.modules):
        raise RuntimeError("Run the baseline in a fresh process before importing Backend")
    if os.getenv("SILICONFLOW_EMBEDDING_MODEL") != "BAAI/bge-m3":
        raise ValueError("Baseline requires the configured BAAI/bge-m3 model")
    if not all(os.getenv(name) for name in ("SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL")):
        raise ValueError("Embedding provider configuration is missing")
    os.environ["RESEARCHFLOW_DATABASE_URL"] = test_url

    from fastapi.testclient import TestClient
    from sqlalchemy import delete, select, text

    from researchflow.backend.app import create_app
    from researchflow.backend.database import SessionLocal, engine
    from researchflow.backend.models import Document, DocumentChunk
    from researchflow.backend.projects import Project

    with engine.connect() as connection:
        if connection.scalar(text("SELECT current_database()")) != "researchflow_test":
            raise RuntimeError("Connected database is not researchflow_test")

    started = datetime.now(timezone.utc).isoformat()
    elapsed_start = monotonic()
    runtime_projects = {}
    runtime_chunks = {}
    cleanup_targets: list[tuple[UUID, UUID]] = []
    cases = []
    cleaned = {"projects": 0, "documents": 0, "chunks": 0}
    try:
        # A fresh application has no dependency overrides: both embedding and
        # ranking use exactly the Product Backend paths, through HTTP requests.
        with TestClient(create_app()) as client:
            for project in fixture.projects:
                owner = uuid4()
                headers = {"X-ResearchFlow-User-Id": str(owner)}
                response = client.post(
                    "/projects", headers=headers,
                    json={"name": f"P7-003C {project.project_key}"[:120]},
                )
                _require_status(response, 201, "Project creation")
                project_id = UUID(response.json()["project_id"])
                cleanup_targets.append((project_id, owner))
                runtime_projects[project.project_key] = (project_id, headers)
                for document in project.documents:
                    response = client.post(
                        f"/projects/{project_id}/documents", headers=headers,
                        files={"file": (
                            document.filename, document.content.encode("utf-8"),
                            "text/markdown",
                        )},
                    )
                    _require_status(response, 201, "Document ingestion")
                    document_id = UUID(response.json()["document_id"])
                    # Read only index, content, and IDs for resolution, never vectors.
                    with SessionLocal() as session:
                        rows = session.execute(
                            select(DocumentChunk.chunk_index, DocumentChunk.chunk_id,
                                   DocumentChunk.content)
                            .where(DocumentChunk.document_id == document_id)
                            .order_by(DocumentChunk.chunk_index)
                        ).all()
                    expected = chunk_markdown(document.content)
                    if [(row.chunk_index, row.content) for row in rows] != [
                        (chunk.chunk_index, chunk.content) for chunk in expected
                    ]:
                        raise RuntimeError("Ingested chunk structure differs from fixture")
                    for row in rows:
                        runtime_chunks[project.project_key, document.document_key,
                                       row.chunk_index] = str(row.chunk_id)

            reverse_chunks = {chunk_id: key for key, chunk_id in runtime_chunks.items()}
            for case in fixture.cases:
                relevant = resolve_relevant(case, runtime_chunks)
                project_id, headers = runtime_projects[case.project_key]
                response = client.post(
                    f"/projects/{project_id}/knowledge/search", headers=headers,
                    json={"query": case.query, "limit": K},
                )
                _require_status(response, 200, "Knowledge search")
                ranked = [hit["chunk_id"] for hit in response.json()]
                if len(ranked) > K or len(set(ranked)) != len(ranked):
                    raise RuntimeError("Invalid ranked result count or duplicate chunks")
                logical_ranked = []
                for chunk_id in ranked:
                    logical = reverse_chunks.get(chunk_id)
                    if logical is None or logical[0] != case.project_key:
                        raise RuntimeError("Search returned a chunk outside evaluation scope")
                    logical_ranked.append({"document_key": logical[1], "chunk_index": logical[2]})
                cases.append({
                    "case_id": case.case_id,
                    "project_key": case.project_key,
                    "relevant_count": len(relevant),
                    "hit_count": len(relevant.intersection(ranked)),
                    "returned_count": len(ranked),
                    "recall_at_5": recall_at_k(relevant, ranked),
                    "ranked_passages": logical_ranked,
                })
    finally:
        # Exact freshly created Project IDs plus owners restrict every DELETE.
        # Existing test rows, development data, sessions and checkpoints are untouched.
        with SessionLocal.begin() as session:
            for project_id, owner in cleanup_targets:
                project = session.scalar(select(Project).where(
                    Project.project_id == project_id, Project.owner_user_id == owner,
                ))
                if project is None:
                    raise RuntimeError("Cleanup target owner/project verification failed")
                document_ids = list(session.scalars(select(Document.document_id).where(
                    Document.project_id == project_id,
                )))
                if document_ids:
                    cleaned["chunks"] += session.execute(delete(DocumentChunk).where(
                        DocumentChunk.document_id.in_(document_ids),
                    )).rowcount
                    cleaned["documents"] += session.execute(delete(Document).where(
                        Document.document_id.in_(document_ids),
                        Document.project_id == project_id,
                    )).rowcount
                session.delete(project)
                cleaned["projects"] += 1
        engine.dispose()

    return {
        "dataset_version": fixture.dataset_version,
        "dataset_sha256": fixture_hash,
        "label_review": fixture.label_review,
        "model": "BAAI/bge-m3",
        "retrieval": "scoped Backend API; pgvector exact cosine",
        "k": K,
        "started_at_utc": started,
        "duration_seconds": round(monotonic() - elapsed_start, 3),
        "candidate_chunks": {
            project.project_key: sum(key[0] == project.project_key for key in runtime_chunks)
            for project in fixture.projects
        },
        "cases": cases,
        "macro_recall_at_5": macro_recall([case["recall_at_5"] for case in cases]),
        "cleanup": cleaned,
        "quality_threshold": None,
        "limitations": "Small synthetic AI-reviewed fixture, not human-reviewed; no answer-quality or release-threshold claim.",
    }


def _require_status(response, expected: int, operation: str) -> None:
    if response.status_code != expected:
        # Do not expose response bodies, request URLs (runtime UUIDs), or credentials.
        raise RuntimeError(f"{operation} failed with HTTP {response.status_code}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.validate_only:
            fixture, digest = load_fixture(args.fixture)
            result = {"dataset_version": fixture.dataset_version,
                      "dataset_sha256": digest, "label_review": fixture.label_review,
                      "cases": len(fixture.cases)}
        else:
            result = run_baseline(args.fixture)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        # Third-party exceptions may include provider headers/DSNs. CLI emits only
        # the exception class; our tests exercise precise errors without secrets.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
