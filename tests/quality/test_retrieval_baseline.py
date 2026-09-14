from copy import deepcopy

import pytest
from pydantic import ValidationError

from evaluations.retrieval import (
    RetrievalFixture,
    load_fixture,
    macro_recall,
    recall_at_k,
    require_test_database,
    resolve_relevant,
)


def test_frozen_fixture_has_nontrivial_candidate_pool():
    from researchflow.knowledge.chunking import chunk_markdown

    fixture, digest = load_fixture()

    assert fixture.dataset_version == "retrieval-v1"
    assert fixture.label_review == "synthetic_ai_reviewed"
    assert len(digest) == 64
    assert sum(len(chunk_markdown(doc.content))
               for project in fixture.projects for doc in project.documents) == 10


@pytest.mark.parametrize("mutation", [
    "duplicate_project", "duplicate_document", "duplicate_case", "duplicate_passage",
    "unknown_project", "unknown_document", "unknown_chunk", "empty_relevance",
    "too_many_relevant", "runtime_id", "negative_index", "boolean_index",
    "trivial_candidates",
])
def test_manifest_rejects_ambiguous_or_invalid_ground_truth(mutation):
    fixture, _ = load_fixture()
    raw = deepcopy(fixture.model_dump())
    project = raw["projects"][0]
    case = raw["cases"][0]
    if mutation == "duplicate_project":
        raw["projects"].append(deepcopy(project))
    elif mutation == "duplicate_document":
        project["documents"].append(deepcopy(project["documents"][0]))
    elif mutation == "duplicate_case":
        raw["cases"].append(deepcopy(case))
    elif mutation == "duplicate_passage":
        case["relevant_passages"].append(deepcopy(case["relevant_passages"][0]))
    elif mutation == "unknown_project":
        case["project_key"] = "missing"
    elif mutation == "unknown_document":
        case["relevant_passages"][0]["document_key"] = "missing"
    elif mutation == "unknown_chunk":
        case["relevant_passages"][0]["chunk_index"] = 100
    elif mutation == "empty_relevance":
        case["relevant_passages"] = []
    elif mutation == "too_many_relevant":
        case["relevant_passages"] *= 3
    elif mutation == "runtime_id":
        case["relevant_passages"][0]["chunk_id"] = "runtime-identity"
    elif mutation == "negative_index":
        case["relevant_passages"][0]["chunk_index"] = -1
    elif mutation == "boolean_index":
        case["relevant_passages"][0]["chunk_index"] = True
    elif mutation == "trivial_candidates":
        for document in project["documents"]:
            document["content"] = "One passage only."

    with pytest.raises(ValidationError):
        RetrievalFixture.model_validate(raw)


@pytest.mark.parametrize(("relevant", "ranked", "expected"), [
    ({"a", "b"}, ["a", "b"], 1.0),
    ({"a", "b"}, ["a", "x"], 0.5),
    ({"a"}, ["x"], 0.0),
    ({"a"}, ["x", "y", "z", "u", "v", "a"], 0.0),
    ({"a", "b"}, ["a", "a", "x"], 0.5),
])
def test_recall_uses_relevant_set_and_only_top_five(relevant, ranked, expected):
    assert recall_at_k(relevant, ranked) == expected


def test_macro_is_unweighted_and_empty_ground_truth_is_rejected():
    assert macro_recall([1.0, 0.5, 0.0]) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        recall_at_k(set(), ["a"])
    with pytest.raises(ValueError):
        macro_recall([])


def test_resolver_survives_new_ingestion_ids_and_enforces_project_scope():
    fixture, _ = load_fixture()
    case = fixture.cases[0]
    first = {
        (case.project_key, "records", 0): "first-a",
        (case.project_key, "records", 1): "first-b",
        ("other-project", "records", 0): "wrong-scope",
    }
    second = {key: f"new-{value}" for key, value in first.items()}

    assert resolve_relevant(case, first) == {"first-a", "first-b"}
    assert resolve_relevant(case, second) == {"new-first-a", "new-first-b"}
    with pytest.raises(ValueError, match="Unresolved"):
        resolve_relevant(case, {("other-project", "records", 0): "wrong-scope"})
    with pytest.raises(ValueError, match="distinct"):
        resolve_relevant(case, {key: "same" for key in first})


@pytest.mark.parametrize("url", [
    None,
    "not-a-url",
    "postgresql+psycopg://user:secret@localhost/researchflow",
    "postgresql+psycopg://user:secret@remote-host/researchflow_test",
    "postgresql+psycopg://user:secret@localhost/researchflow_test?dbname=researchflow",
    "sqlite:///researchflow_test",
])
def test_database_guard_rejects_nonisolated_targets_without_echoing_credentials(url):
    with pytest.raises(ValueError) as error:
        require_test_database(url)
    assert "secret" not in str(error.value)


def test_database_guard_accepts_only_explicit_local_test_target():
    url = "postgresql+psycopg://user:secret@127.0.0.1:5432/researchflow_test"
    assert require_test_database(url) == url
