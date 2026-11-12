"""Dataset schemas, normalized view, and mechanical label validation.

Two on-disk schema versions are supported:

``schema_version: 1``
    The legacy three-case fixture (``retrieval_v1.json``). It remains loadable
    through the new runner but cannot express hard negatives, difficulty, or
    abstention cases.

``schema_version: 2``
    The 50-case evaluation set (``datasets/retrieval_v2.json``). Every
    referenced passage carries an ``anchor`` substring so the label can be
    checked against the real chunker without a database, embeddings, or API.

The important guarantee is that a ``chunk_index`` is never trusted on its own:
:func:`load_eval_dataset` re-chunks every document with
``researchflow.knowledge.chunking.chunk_markdown`` and fails loudly when a
passage points at a missing chunk, an unknown document, or a chunk that does
not literally contain the declared anchor.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from researchflow.knowledge.chunking import chunk_markdown

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = PACKAGE_DIR / "datasets" / "retrieval_v2.json"
RETRIEVAL_V1_PATH = PACKAGE_DIR / "retrieval_v1.json"

MAX_DOCUMENT_BYTES = 1_048_576
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class DatasetValidationError(ValueError):
    """Raised when a dataset is structurally invalid or its labels are wrong."""


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# schema_version 1 (legacy, frozen)
# ---------------------------------------------------------------------------


class PassageV1(FixtureModel):
    document_key: str = Field(min_length=1)
    chunk_index: int = Field(ge=0)


class DocumentV1(FixtureModel):
    document_key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00]+\.md$")
    content: str = Field(min_length=1)


class ProjectV1(FixtureModel):
    project_key: str = Field(min_length=1)
    documents: list[DocumentV1] = Field(min_length=1)


class CaseV1(FixtureModel):
    case_id: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=2000)
    relevant_passages: list[PassageV1] = Field(min_length=1, max_length=5)
    rationale: str = Field(min_length=1)


class RetrievalDatasetV1(FixtureModel):
    schema_version: Literal[1]
    dataset_version: str = Field(min_length=1)
    label_review: Literal["synthetic_ai_reviewed"]
    label_note: str = Field(min_length=1)
    projects: list[ProjectV1] = Field(min_length=1)
    cases: list[CaseV1] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_v1_references(self):
        _unique([project.project_key for project in self.projects], "project_key")
        _unique([case.case_id for case in self.cases], "case_id")
        chunks: dict[tuple[str, str], int] = {}
        candidate_counts: dict[str, int] = {}
        for project in self.projects:
            _unique([document.document_key for document in project.documents], "document_key")
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
            if candidate_counts.get(case.project_key, 0) <= 5:
                raise ValueError("Each evaluated Project must contain more than 5 passages")
            _unique(
                [(passage.document_key, passage.chunk_index) for passage in case.relevant_passages],
                "relevant passage",
            )
            for passage in case.relevant_passages:
                count = chunks.get((case.project_key, passage.document_key), 0)
                if passage.chunk_index >= count:
                    raise ValueError(
                        f"Case {case.case_id!r} references a missing Document/chunk"
                    )
        return self


# ---------------------------------------------------------------------------
# schema_version 2 (evaluation set)
# ---------------------------------------------------------------------------


class PassageV2(FixtureModel):
    document_key: str = Field(min_length=1, max_length=200)
    chunk_index: int = Field(ge=0)
    anchor: str = Field(min_length=3, max_length=500)


class DocumentV2(FixtureModel):
    document_key: str = Field(min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\\x00]+\.md$")
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_must_fit_backend_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError("Document exceeds the 1 MiB Product Backend limit")
        return value


class ProjectV2(FixtureModel):
    project_key: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    documents: list[DocumentV2] = Field(min_length=3, max_length=6)


class CaseV2(FixtureModel):
    case_id: str = Field(min_length=1, max_length=200)
    project_key: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)
    relevant_passages: list[PassageV2] = Field(default_factory=list, max_length=20)
    distractor_passages: list[PassageV2] = Field(default_factory=list, max_length=20)
    rationale: str = Field(min_length=1)
    difficulty: Literal["easy", "medium", "hard"]

    @model_validator(mode="after")
    def validate_passage_sets(self):
        relevant = [(passage.document_key, passage.chunk_index) for passage in self.relevant_passages]
        distractors = [
            (passage.document_key, passage.chunk_index) for passage in self.distractor_passages
        ]
        _unique(relevant, "relevant passage")
        _unique(distractors, "distractor passage")
        if set(relevant).intersection(distractors):
            raise ValueError("A passage cannot be both relevant and a distractor")
        return self


class RetrievalDatasetV2(FixtureModel):
    schema_version: Literal[2]
    dataset_version: str = Field(min_length=1)
    label_review: Literal["synthetic_ai_reviewed"]
    label_note: str = Field(min_length=1)
    # Chunker settings the chunk_index labels were produced under. Optional so
    # earlier datasets stay loadable; the loader refuses a mismatch.
    chunking: dict | None = None
    projects: list[ProjectV2] = Field(min_length=1)
    cases: list[CaseV2] = Field(min_length=50, max_length=50)

    @model_validator(mode="after")
    def validate_v2_references(self):
        _unique([project.project_key for project in self.projects], "project_key")
        _unique([case.case_id for case in self.cases], "case_id")
        project_keys = {project.project_key for project in self.projects}
        for project in self.projects:
            _unique([document.document_key for document in project.documents], "document_key")
        for case in self.cases:
            if case.project_key not in project_keys:
                raise ValueError(
                    f"Case {case.case_id!r} references unknown project_key {case.project_key!r}"
                )
        return self


# ---------------------------------------------------------------------------
# Normalized, schema-independent view consumed by the runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalPassage:
    document_key: str
    chunk_index: int
    anchor: str | None = None

    @property
    def key(self) -> tuple[str, int]:
        return (self.document_key, self.chunk_index)


@dataclass(frozen=True)
class EvalDocument:
    document_key: str
    filename: str
    content: str
    chunks: tuple[str, ...]


@dataclass(frozen=True)
class EvalProject:
    project_key: str
    name: str
    documents: tuple[EvalDocument, ...]

    def document(self, document_key: str) -> EvalDocument | None:
        for document in self.documents:
            if document.document_key == document_key:
                return document
        return None


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    project_key: str
    query: str
    relevant_passages: tuple[EvalPassage, ...]
    distractor_passages: tuple[EvalPassage, ...]
    rationale: str
    difficulty: str

    @property
    def relevant_keys(self) -> tuple[tuple[str, int], ...]:
        return tuple(passage.key for passage in self.relevant_passages)

    @property
    def distractor_keys(self) -> tuple[tuple[str, int], ...]:
        return tuple(passage.key for passage in self.distractor_passages)

    @property
    def is_unanswerable(self) -> bool:
        return not self.relevant_passages

    @property
    def is_cross_lingual(self) -> bool:
        return bool(_CJK.search(self.query))

    @property
    def is_multi_hop(self) -> bool:
        return len({passage.document_key for passage in self.relevant_passages}) >= 2

    @property
    def is_hard_negative(self) -> bool:
        return bool(self.distractor_passages)


@dataclass(frozen=True)
class EvalDataset:
    schema_version: int
    dataset_version: str
    label_review: str
    label_note: str
    projects: tuple[EvalProject, ...]
    cases: tuple[EvalCase, ...]

    def project(self, project_key: str) -> EvalProject | None:
        for project in self.projects:
            if project.project_key == project_key:
                return project
        return None


@dataclass(frozen=True)
class DatasetComposition:
    projects: int
    documents: int
    chunks: int
    cases: int
    easy: int
    medium: int
    hard: int
    unspecified: int
    hard_negative: int
    multi_hop: int
    cross_lingual: int
    unanswerable: int

    def as_dict(self) -> dict[str, int]:
        return {
            "projects": self.projects,
            "documents": self.documents,
            "chunks": self.chunks,
            "cases": self.cases,
            "easy": self.easy,
            "medium": self.medium,
            "hard": self.hard,
            "unspecified": self.unspecified,
            "hard_negative": self.hard_negative,
            "multi_hop": self.multi_hop,
            "cross_lingual": self.cross_lingual,
            "unanswerable": self.unanswerable,
        }


def is_cross_lingual_query(query: str) -> bool:
    return bool(_CJK.search(query))


def _unique(values, label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


def _format_validation_error(error: ValidationError) -> str:
    parts = []
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "<root>"
        parts.append(f"{location}: {item['msg']}")
    return "; ".join(parts)


def _normalize_v1(model: RetrievalDatasetV1) -> EvalDataset:
    projects = []
    for project in model.projects:
        documents = []
        for document in project.documents:
            chunks = tuple(chunk.content for chunk in chunk_markdown(document.content))
            documents.append(
                EvalDocument(document.document_key, document.filename, document.content, chunks)
            )
        projects.append(EvalProject(project.project_key, project.project_key, tuple(documents)))
    cases = tuple(
        EvalCase(
            case_id=case.case_id,
            project_key=case.project_key,
            query=case.query,
            relevant_passages=tuple(
                EvalPassage(passage.document_key, passage.chunk_index) for passage in case.relevant_passages
            ),
            distractor_passages=(),
            rationale=case.rationale,
            difficulty="unspecified",
        )
        for case in model.cases
    )
    return EvalDataset(
        schema_version=model.schema_version,
        dataset_version=model.dataset_version,
        label_review=model.label_review,
        label_note=model.label_note,
        projects=tuple(projects),
        cases=cases,
    )


def _normalize_v2(model: RetrievalDatasetV2) -> EvalDataset:
    projects = []
    for project in model.projects:
        documents = []
        for document in project.documents:
            chunks = tuple(chunk.content for chunk in chunk_markdown(document.content))
            documents.append(
                EvalDocument(document.document_key, document.filename, document.content, chunks)
            )
        projects.append(EvalProject(project.project_key, project.name, tuple(documents)))
    cases = tuple(
        EvalCase(
            case_id=case.case_id,
            project_key=case.project_key,
            query=case.query,
            relevant_passages=tuple(
                EvalPassage(passage.document_key, passage.chunk_index, passage.anchor)
                for passage in case.relevant_passages
            ),
            distractor_passages=tuple(
                EvalPassage(passage.document_key, passage.chunk_index, passage.anchor)
                for passage in case.distractor_passages
            ),
            rationale=case.rationale,
            difficulty=case.difficulty,
        )
        for case in model.cases
    )
    return EvalDataset(
        schema_version=model.schema_version,
        dataset_version=model.dataset_version,
        label_review=model.label_review,
        label_note=model.label_note,
        projects=tuple(projects),
        cases=cases,
    )


def _validate_labels(dataset: EvalDataset, source: Path) -> None:
    """Check every referenced passage against the real chunker.

    ``chunk_index`` is derived from ``chunk_markdown``; a label is only
    trustworthy when the index exists *and* the declared anchor is literally in
    that chunk.
    """
    documents = {}
    for project in dataset.projects:
        for document in project.documents:
            if not document.chunks:
                raise DatasetValidationError(
                    f"{source}: project {project.project_key!r} document "
                    f"{document.document_key!r} produced no chunks"
                )
            documents[project.project_key, document.document_key] = document

    for case in dataset.cases:
        if dataset.project(case.project_key) is None:
            raise DatasetValidationError(
                f"{source}: case {case.case_id!r} references unknown project_key "
                f"{case.project_key!r}"
            )
        for passage in case.relevant_passages:
            _check_passage(case, passage, documents, source, "relevant")
        for passage in case.distractor_passages:
            _check_passage(case, passage, documents, source, "distractor")


def _check_passage(case, passage, documents, source, role: str) -> None:
    document = documents.get((case.project_key, passage.document_key))
    if document is None:
        raise DatasetValidationError(
            f"{source}: case {case.case_id!r} {role} passage references unknown "
            f"document_key {passage.document_key!r} in project {case.project_key!r}"
        )
    if passage.chunk_index >= len(document.chunks):
        raise DatasetValidationError(
            f"{source}: case {case.case_id!r} {role} passage references chunk_index "
            f"{passage.chunk_index} but document {passage.document_key!r} has "
            f"{len(document.chunks)} chunk(s)"
        )
    if passage.anchor is not None:
        chunk = document.chunks[passage.chunk_index]
        if passage.anchor not in chunk:
            raise DatasetValidationError(
                f"{source}: case {case.case_id!r} {role} anchor {passage.anchor!r} "
                f"does not appear in {passage.document_key!r} chunk {passage.chunk_index}"
            )


def load_eval_dataset(path: Path = DEFAULT_DATASET) -> tuple[EvalDataset, str]:
    """Load, schema-validate, and label-validate a dataset.

    Returns the normalized dataset plus the SHA-256 of the exact file bytes.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise DatasetValidationError(f"{path}: cannot read dataset: {error}") from None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DatasetValidationError(f"{path}: not valid JSON: {error}") from None
    if not isinstance(payload, dict):
        raise DatasetValidationError(f"{path}: dataset root must be a JSON object")

    version = payload.get("schema_version")
    if version == 1:
        model_class = RetrievalDatasetV1
        normalize = _normalize_v1
    elif version == 2:
        model_class = RetrievalDatasetV2
        normalize = _normalize_v2
    else:
        raise DatasetValidationError(
            f"{path}: unsupported schema_version {version!r}; "
            f"expected one of {SUPPORTED_SCHEMA_VERSIONS}"
        )

    try:
        model = model_class.model_validate(payload)
    except ValidationError as error:
        raise DatasetValidationError(
            f"{path}: schema validation failed: {_format_validation_error(error)}"
        ) from None

    _check_chunking_config(payload, path)

    dataset = normalize(model)
    _validate_labels(dataset, path)
    return dataset, digest


def _check_chunking_config(payload: dict, path: Path) -> None:
    """Refuse to read a dataset under different chunking settings.

    A ``chunk_index`` label only means something under the chunker that produced
    it. Without this check, running the evaluation under a different
    ``RESEARCHFLOW_CHUNK_CHARS`` fails later with a confusing "anchor not in
    chunk" error that looks like a broken label.
    """

    from researchflow.knowledge.chunking import CHUNK_OVERLAP_CHARS, MAX_CHUNK_CHARS

    recorded = payload.get("chunking")
    if not isinstance(recorded, dict):
        return

    expected = {
        "max_chars": recorded.get("max_chars"),
        "overlap_chars": recorded.get("overlap_chars"),
    }
    actual = {
        "max_chars": MAX_CHUNK_CHARS,
        "overlap_chars": CHUNK_OVERLAP_CHARS,
    }
    if expected != actual:
        raise DatasetValidationError(
            f"{path}: built with chunking {expected} but this process uses {actual}. "
            "Set RESEARCHFLOW_CHUNK_CHARS / RESEARCHFLOW_CHUNK_OVERLAP to match the "
            "dataset, or rebuild the dataset under the current settings "
            "(scripts/build_eval_corpus.py)."
        )


def composition(dataset: EvalDataset) -> DatasetComposition:
    difficulty = {"easy": 0, "medium": 0, "hard": 0, "unspecified": 0}
    for case in dataset.cases:
        difficulty[case.difficulty] += 1
    return DatasetComposition(
        projects=len(dataset.projects),
        documents=sum(len(project.documents) for project in dataset.projects),
        chunks=sum(
            len(document.chunks)
            for project in dataset.projects
            for document in project.documents
        ),
        cases=len(dataset.cases),
        easy=difficulty["easy"],
        medium=difficulty["medium"],
        hard=difficulty["hard"],
        unspecified=difficulty["unspecified"],
        hard_negative=sum(1 for case in dataset.cases if case.is_hard_negative),
        multi_hop=sum(1 for case in dataset.cases if case.is_multi_hop),
        cross_lingual=sum(1 for case in dataset.cases if case.is_cross_lingual),
        unanswerable=sum(1 for case in dataset.cases if case.is_unanswerable),
    )
