"""Pins what ``retrieval-v3`` is, so it cannot be mistaken for a better corpus.

``retrieval_v3.json`` was produced by appending one generated "background" note
to every Project. Those notes are not realistic documents: 1,320 paragraphs
collapse to six templates, each repeated about 220 times with an incrementing
record number.

A corpus like that does not make retrieval harder in a way that means anything.
The filler is generic across its whole domain, so it either sits far from every
concrete query (and changes nothing) or crowds the window with near-duplicates
(and depresses Recall for a reason that does not generalise). Either way the
number it produces is about the filler, not about the retriever.

These tests therefore document v3 as a *filler stress fixture*: valid enough to
exercise loading and scoring, explicitly not the default corpus, and not
evidence of quality.
"""

import re

import pytest

from evaluations.dataset import DEFAULT_DATASET, load_eval_dataset

V3_PATH = DEFAULT_DATASET.parent / "retrieval_v3.json"


@pytest.fixture(scope="module")
def v3():
    return load_eval_dataset(V3_PATH)[0]


def _background_paragraphs(dataset) -> list[str]:
    paragraphs: list[str] = []
    for project in dataset.projects:
        for document in project.documents:
            if not document.document_key.endswith("-background"):
                continue
            paragraphs.extend(
                part.strip()
                for part in document.content.split("\n\n")
                if part.strip()
                and not part.strip().startswith("#")
                and not part.strip().startswith("Supplemental")
            )
    return paragraphs


def _template(text: str) -> str:
    return re.sub(r"\d+", "#", text).lower()


def test_v3_is_not_the_default_evaluation_dataset():
    assert DEFAULT_DATASET.name == "retrieval_v2.json"
    assert V3_PATH.name == "retrieval_v3.json"


def test_v3_loads_and_keeps_the_fifty_case_labels(v3):
    assert v3.dataset_version == "retrieval-v3"
    assert len(v3.cases) == 50
    assert len(v3.projects) == 6


def test_v3_background_notes_are_a_handful_of_templates(v3):
    paragraphs = _background_paragraphs(v3)

    assert len(paragraphs) >= 1000

    templates = {_template(text) for text in paragraphs}

    # If this ever fails, someone replaced the filler with real prose - which
    # would make v3 a legitimate corpus worth wiring up as the default.
    assert len(templates) <= 8, (
        f"retrieval-v3 now has {len(templates)} distinct background templates; "
        "if that is real prose, promote it to the default corpus and delete this test"
    )


def test_v3_growth_is_padding_not_documentation(v3):
    paragraphs = _background_paragraphs(v3)
    dominant = max(
        sum(1 for text in paragraphs if _template(text) == _template(paragraphs[0])),
        len(paragraphs) - 1,
    )
    assert dominant / len(paragraphs) > 0.2
