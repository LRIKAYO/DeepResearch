"""Tests for the frozen retrieval-v1 fixture through the new evaluation package.

This file was updated when ``evaluations/retrieval.py`` was retired:

* imports moved to ``evaluations.dataset`` / ``evaluations.metrics``;
* the database-guard tests were removed because the replacement runner is
  API-only and never opens a database connection, so the old
  ``RESEARCHFLOW_TEST_DATABASE_URL`` guard no longer exists;
* the old runtime-ID resolver test was replaced by a loader-level test that the
  same v1 passage keys resolve against the real chunker and that a corrupt
  chunk reference fails loudly.

The v1 fixture itself is untouched and remains loadable through
``evaluations.run_eval --dataset evaluations/retrieval_v1.json``.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluations.dataset import (
    RETRIEVAL_V1_PATH,
    DatasetValidationError,
    RetrievalDatasetV1,
    load_eval_dataset,
)
from evaluations.metrics import macro_recall, recall_at_k
from researchflow.knowledge.chunking import chunk_markdown


def _v1_raw() -> dict:
    return json.loads(RETRIEVAL_V1_PATH.read_text(encoding="utf-8"))


def test_frozen_fixture_has_nontrivial_candidate_pool():
    from researchflow.knowledge.chunking import chunk_markdown

    dataset, digest = load_eval_dataset(RETRIEVAL_V1_PATH)

    assert dataset.schema_version == 1
    assert dataset.dataset_version == "retrieval-v1"
    assert dataset.label_review == "synthetic_ai_reviewed"
    assert len(digest) == 64
    assert sum(len(chunk_markdown(doc.content))
               for project in dataset.projects for doc in project.documents) == 10
    assert len(dataset.cases) == 3


@pytest.mark.parametrize("mutation", [
    "duplicate_project", "duplicate_document", "duplicate_case", "duplicate_passage",
    "unknown_project", "unknown_document", "unknown_chunk", "empty_relevance",
    "too_many_relevant", "runtime_id", "negative_index", "boolean_index",
    "trivial_candidates",
])
def test_manifest_rejects_ambiguous_or_invalid_ground_truth(mutation):
    raw = _v1_raw()
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
        RetrievalDatasetV1.model_validate(raw)


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


def test_v1_passage_keys_resolve_against_the_real_chunker():
    dataset, _ = load_eval_dataset(RETRIEVAL_V1_PATH)
    case = dataset.cases[0]

    assert case.relevant_keys == (("records", 0), ("records", 1))
    for project in dataset.projects:
        for document in project.documents:
            assert len(document.chunks) == len(chunk_markdown(document.content))


def test_v1_corrupt_chunk_fails_loudly_and_names_the_case(tmp_path: Path):
    raw = _v1_raw()
    raw["cases"][0]["relevant_passages"][0]["chunk_index"] = 999
    path = tmp_path / "broken_v1.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(DatasetValidationError) as error:
        load_eval_dataset(path)
    message = str(error.value)
    assert "archive-backup-schedule" in message
    assert "missing Document/chunk" in message
