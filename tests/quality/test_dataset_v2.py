"""Dataset-level tests for the 50-case retrieval-v2 evaluation set.

These tests are fully offline: they re-chunk the Markdown with the production
chunker and never touch the backend, embeddings, or a database.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from evaluations.dataset import (
    DEFAULT_DATASET,
    RETRIEVAL_V1_PATH,
    DatasetValidationError,
    composition,
    load_eval_dataset,
)
from researchflow.knowledge.chunking import chunk_markdown


@pytest.fixture(scope="module")
def dataset():
    return load_eval_dataset()[0]


def _raw() -> dict:
    return json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))


def test_schema_is_versioned_and_complete(dataset):
    assert dataset.schema_version == 2
    assert dataset.dataset_version == "retrieval-v2"
    assert dataset.label_review == "synthetic_ai_reviewed"
    assert len(dataset.projects) == 6
    assert len(dataset.cases) == 50
    assert len({case.case_id for case in dataset.cases}) == 50
    assert all(3 <= len(project.documents) <= 6 for project in dataset.projects)



def test_composition_meets_required_minimums(dataset):
    counts = composition(dataset)
    assert counts.projects == 6
    assert counts.documents == 24
    assert counts.cases == 50
    assert counts.hard_negative >= 12
    assert counts.multi_hop >= 6
    assert counts.cross_lingual >= 4
    assert counts.unanswerable >= 4
    assert counts.easy > 0 and counts.medium > 0 and counts.hard > 0


def test_composition_is_pinned_to_this_dataset(dataset):
    """Changing these counts is a deliberate dataset revision, not an accident."""
    assert composition(dataset).as_dict() == {
        "projects": 6,
        "documents": 24,
        "chunks": 122,
        "cases": 50,
        "easy": 10,
        "medium": 25,
        "hard": 15,
        "unspecified": 0,
        "hard_negative": 28,
        "multi_hop": 6,
        "cross_lingual": 6,
        "unanswerable": 5,
    }


def test_every_referenced_chunk_exists_and_contains_its_anchor(dataset):
    """The mechanical label-consistency guarantee, independent of the loader."""
    chunks: dict[tuple[str, str], list[str]] = {}
    for project in dataset.projects:
        for document in project.documents:
            chunks[project.project_key, document.document_key] = [
                chunk.content for chunk in chunk_markdown(document.content)
            ]

    for case in dataset.cases:
        assert case.rationale.strip()
        for passage in case.relevant_passages + case.distractor_passages:
            key = (case.project_key, passage.document_key)
            assert key in chunks, f"{case.case_id}: unknown document {passage.document_key}"
            assert passage.chunk_index < len(chunks[key]), (
                f"{case.case_id}: chunk {passage.chunk_index} missing from "
                f"{passage.document_key}"
            )
            assert passage.anchor is not None
            assert passage.anchor in chunks[key][passage.chunk_index], (
                f"{case.case_id}: anchor {passage.anchor!r} is not in "
                f"{passage.document_key}[{passage.chunk_index}]"
            )


def test_case_flags_are_truthful(dataset):
    for case in dataset.cases:
        if case.is_unanswerable:
            assert case.relevant_keys == ()
            assert "abstain" in case.rationale.lower()
        if case.is_multi_hop:
            document_keys = {passage.document_key for passage in case.relevant_passages}
            assert len(document_keys) >= 2
            assert len(case.relevant_passages) >= 2
        if case.is_cross_lingual:
            assert any("\u4e00" <= character <= "\u9fff" for character in case.query)
        if case.is_hard_negative:
            assert case.distractor_passages
            assert set(case.relevant_keys).isdisjoint(case.distractor_keys)


def test_projects_cover_six_named_domains(dataset):
    assert {project.project_key for project in dataset.projects} == {
        "lab-operations",
        "api-documentation",
        "hr-policy",
        "clinical-protocol",
        "finance-policy",
        "product-spec",
    }
    for project in dataset.projects:
        assert project.name.strip()
        for document in project.documents:
            assert document.content.startswith("# ")
            assert "\n## " in document.content


def test_v1_fixture_still_loads_through_the_loader():
    dataset, digest = load_eval_dataset(RETRIEVAL_V1_PATH)
    assert dataset.schema_version == 1
    assert len(digest) == 64
    assert len(dataset.cases) == 3
    assert composition(dataset).cases == 3


def test_digest_is_deterministic():
    _, first = load_eval_dataset()
    _, second = load_eval_dataset()
    assert first == second
    assert len(first) == 64


def _write_mutated(tmp_path: Path, mutate) -> Path:
    raw = _raw()
    mutate(raw)
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        ("unknown_relevant_document", "unknown document_key"),
        ("unknown_distractor_document", "unknown document_key"),
        ("missing_relevant_chunk", "chunk_index 999"),
        ("missing_distractor_chunk", "chunk_index 999"),
        ("wrong_anchor", "anchor"),
        ("unknown_project", "unknown project_key"),
        ("duplicate_case", "Duplicate case_id"),
        ("wrong_difficulty", "difficulty"),
        ("too_few_cases", "at least 50"),
    ],
)
def test_invalid_dataset_fails_loudly(tmp_path, mutation, fragment):
    def mutate(raw: dict) -> None:
        case = raw["cases"][0]
        if mutation == "unknown_relevant_document":
            case["relevant_passages"][0]["document_key"] = "does-not-exist"
        elif mutation == "unknown_distractor_document":
            candidate = next(c for c in raw["cases"] if c["distractor_passages"])
            candidate["distractor_passages"][0]["document_key"] = "does-not-exist"
        elif mutation == "missing_relevant_chunk":
            case["relevant_passages"][0]["chunk_index"] = 999
        elif mutation == "missing_distractor_chunk":
            candidate = next(c for c in raw["cases"] if c["distractor_passages"])
            candidate["distractor_passages"][0]["chunk_index"] = 999
        elif mutation == "wrong_anchor":
            case["relevant_passages"][0]["anchor"] = "this-anchor-is-not-in-the-chunk"
        elif mutation == "unknown_project":
            case["project_key"] = "does-not-exist"
        elif mutation == "duplicate_case":
            raw["cases"][1] = deepcopy(case)
        elif mutation == "wrong_difficulty":
            case["difficulty"] = "impossible"
        elif mutation == "too_few_cases":
            raw["cases"].pop()

    path = _write_mutated(tmp_path, mutate)
    with pytest.raises(DatasetValidationError) as error:
        load_eval_dataset(path)
    assert fragment in str(error.value)
