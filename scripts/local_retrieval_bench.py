"""Rank the evaluation corpus locally and emit a ``run_eval --replay`` fixture.

Why this exists: producing a retrieval number normally means standing up
PostgreSQL + pgvector and the Product Backend, uploading 36 documents and
searching through the HTTP API. When that stack is unavailable, the retrieval
*computation* can still be exercised exactly: the same chunker, the same
embedding model, and the same exact cosine similarity the Backend performs
(pgvector's ``<=>`` is exact here — the schema has no ANN index).

What this does **not** exercise: document upload, the Product Backend request
path, PostgreSQL, and latency. The fixture's ``note`` says so, and the report
``run_eval --replay`` renders it into the Markdown header, so the caveat cannot
be lost on regeneration.

Usage::

    py -3.12 -m scripts.local_retrieval_bench --dataset evaluations/datasets/retrieval_v4.json --out evaluations/reports/v4-ranking.json
    py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v4.json --replay evaluations/reports/v4-ranking.json --k 5 --out evaluations/reports/v4-local.md --json-out evaluations/reports/v4-local.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from evaluations.dataset import load_eval_dataset
from researchflow.knowledge.embeddings import build_embeddings, embed_documents, embed_query

NOTE = (
    "Rankings computed offline by this repository's own chunker and the configured "
    "embedding model (bge-m3) with exact cosine similarity - the same computation "
    "the Product Backend performs over pgvector, but without the HTTP API, the "
    "database, or document upload. Latency is therefore not measured, and this run "
    "is not evidence that the upload path works."
)


def _load_env(path: Path) -> None:
    import os

    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _normalised(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--only-project",
        default=None,
        help="embed and rank one Project only (smoke test)",
    )
    args = parser.parse_args(argv)

    _load_env(args.env_file)

    dataset, digest = load_eval_dataset(args.dataset)
    embeddings = build_embeddings()

    started = time.time()
    cases = list(dataset.cases)
    if args.only_project:
        cases = [case for case in cases if case.project_key == args.only_project]

    needed_projects = {case.project_key for case in cases}
    rankings: dict[str, dict] = {}

    for project_key in sorted(needed_projects):
        project = dataset.project(project_key)
        assert project is not None

        passages: list[tuple[str, int]] = []
        texts: list[str] = []
        for document in project.documents:
            for index, chunk in enumerate(document.chunks):
                passages.append((document.document_key, index))
                texts.append(chunk)

        print(
            f"{project_key}: embedding {len(texts)} chunks ...",
            flush=True,
        )
        project_started = time.time()
        vectors = np.asarray(embed_documents(embeddings, texts), dtype=np.float32)
        matrix = _normalised(vectors)
        print(
            f"  done in {time.time() - project_started:.1f}s "
            f"({vectors.shape[0]}x{vectors.shape[1]})",
            flush=True,
        )

        for case in [item for item in cases if item.project_key == project_key]:
            query_vector = np.asarray(embed_query(embeddings, case.query), dtype=np.float32)
            norm = float(np.linalg.norm(query_vector)) or 1.0
            scores = matrix @ (query_vector / norm)
            order = np.argsort(-scores)[: args.k]
            rankings[case.case_id] = {
                "case_id": case.case_id,
                "ranked_passages": [
                    {
                        "document_key": passages[position][0],
                        "chunk_index": passages[position][1],
                        "score": round(float(scores[position]), 6),
                    }
                    for position in order
                ],
            }

    fixture = {
        "schema_version": 1,
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": digest,
        "k": args.k,
        "note": NOTE,
        "cases": [rankings[case.case_id] for case in cases],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {args.out} ({len(fixture['cases'])} cases) "
        f"in {time.time() - started:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
