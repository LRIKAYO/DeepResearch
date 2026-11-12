"""Guards for the real-document evaluation corpus.

Two layers:

* pure-function tests for the builder, which are fast and need no install;
* dataset-level tests over the committed ``retrieval_v4.json``, which assert the
  properties the earlier generated corpus failed — real attribution per section,
  no template padding, and enough chunks per Project for k=5 to mean something.
"""

import re
from pathlib import Path

import pytest

from evaluations.dataset import load_eval_dataset
from researchflow.knowledge.chunking import chunk_markdown
from scripts.build_eval_corpus import (
    VOLUMES_PER_PROJECT,
    PackageDoc,
    _clean,
    build_volumes,
    classify,
)

V4_PATH = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "evaluations"
    / "datasets"
    / "retrieval_v4.json"
)


# --- builder, pure functions -------------------------------------------------


def test_classification_covers_the_expected_families():
    assert classify("d3-shape") == "data-visualisation"
    assert classify("micromark-util-types") == "markdown-pipeline"
    assert classify("eslint-plugin-react") == "testing-and-lint"
    assert classify("p-queue") == "http-and-async-runtime"
    assert classify("@langchain/core") == "http-and-async-runtime"
    assert classify("enhanced-resolve") == "build-and-tooling"
    assert classify("zod") == "schemas-and-utilities"


def test_clean_drops_badges_and_html_comments():
    raw = "\n".join(
        [
            "# Title",
            "[![build](https://img.shields.io/x.svg)](https://ci)",
            "![logo](logo.png)",
            "<!-- hidden -->",
            "Real prose about behaviour.",
        ]
    )

    cleaned = _clean(raw)

    assert "Real prose about behaviour." in cleaned
    assert "shields.io" not in cleaned
    assert "logo.png" not in cleaned
    assert "hidden" not in cleaned


def test_build_volumes_spreads_packages_and_records_licences():
    packages = [
        PackageDoc(
            name=f"pkg-{index}",
            path=__import__("pathlib").Path(f"pkg-{index}/README.md"),
            license="MIT",
            text=f"# pkg-{index}\n\nReal content for package {index}.",
        )
        for index in range(12)
    ]

    volumes = build_volumes(packages, project_key="demo", project_name="Demo")

    assert len(volumes) == VOLUMES_PER_PROJECT
    joined = "\n".join(volume["content"] for volume in volumes)
    for index in range(12):
        assert f"## pkg-{index}" in joined
    assert "licence: MIT" in joined


# --- committed dataset -------------------------------------------------------


@pytest.fixture(scope="module")
def dataset():
    return load_eval_dataset(V4_PATH)[0]


def test_six_projects_with_exactly_six_volumes(dataset):
    assert len(dataset.projects) == 6
    for project in dataset.projects:
        assert len(project.documents) == VOLUMES_PER_PROJECT
        keys = [document.document_key for document in project.documents]
        assert len(keys) == len(set(keys))
        for document in project.documents:
            assert document.filename.endswith(".md")
            assert "/" not in document.filename


def test_every_project_is_large_enough_for_top_five_to_mean_something(dataset):
    for project in dataset.projects:
        chunks = sum(len(document.chunks) for document in project.documents)
        assert chunks >= 200, f"{project.project_key} has only {chunks} chunks"


def test_every_volume_names_its_sources_and_licences(dataset):
    for project in dataset.projects:
        for document in project.documents:
            assert "Source: `" in document.content
            assert "licence:" in document.content


def test_corpus_is_not_template_padding(dataset):
    """The retrieval-v3 regression: 1,320 paragraphs that collapsed to 6 templates."""

    for project in dataset.projects:
        paragraphs = []
        for document in project.documents:
            paragraphs.extend(
                part.strip()
                for part in document.content.split("\n\n")
                if len(part.strip()) > 120
            )
        templates = {re.sub(r"\d+", "#", paragraph).lower() for paragraph in paragraphs}
        ratio = len(templates) / max(len(paragraphs), 1)
        assert ratio > 0.8, (
            f"{project.project_key} has only {len(templates)} distinct bodies "
            f"across {len(paragraphs)} paragraphs"
        )


def test_cases_cover_all_six_projects_and_the_expected_shape(dataset):
    assert len(dataset.cases) == 50

    per_project = {}
    for case in dataset.cases:
        per_project[case.project_key] = per_project.get(case.project_key, 0) + 1
    assert set(per_project) == {project.project_key for project in dataset.projects}
    assert min(per_project.values()) >= 8

    answerable = [case for case in dataset.cases if case.relevant_passages]
    assert len(answerable) >= 40
    assert sum(1 for case in dataset.cases if case.is_cross_lingual) >= 5
    assert sum(1 for case in dataset.cases if case.is_multi_hop) >= 6
    assert sum(1 for case in dataset.cases if case.distractor_passages) >= 20


def test_every_anchor_sits_inside_its_chunk(dataset):
    """The loader already checks this; keep an explicit, readable assertion."""

    for case in dataset.cases:
        for passage in list(case.relevant_passages) + list(case.distractor_passages):
            project = dataset.project(case.project_key)
            assert project is not None
            document = project.document(passage.document_key)
            assert document is not None
            chunk = document.chunks[passage.chunk_index]
            assert passage.anchor in chunk, case.case_id


def test_dataset_refuses_a_chunking_mismatch(tmp_path):
    """A chunk_index label only means something under the chunker that built it."""

    import json

    from evaluations.dataset import DatasetValidationError, load_eval_dataset

    source = json.loads(
        (Path(__file__).resolve().parents[2] / "evaluations/datasets/retrieval_v4.json")
        .read_text(encoding="utf-8-sig")
    )
    source["chunking"] = {"max_chars": 123, "overlap_chars": 7}

    target = tmp_path / "dataset.json"
    target.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="built with chunking"):
        load_eval_dataset(target)


def test_dataset_records_its_chunking_config():
    import json

    raw = json.loads(
        (Path(__file__).resolve().parents[2] / "evaluations/datasets/retrieval_v4.json")
        .read_text(encoding="utf-8-sig")
    )

    assert raw["chunking"] == {"max_chars": 2000, "overlap_chars": 0}
