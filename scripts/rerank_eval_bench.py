"""Benchmark hybrid retrieval + cross-encoder reranking offline on an eval dataset.

Computes exact ``bge-m3`` cosine similarities + in-process BM25/RRF +
``HttpReranker`` (``BAAI/bge-reranker-v2-m3`` by default) through the repository's
own ``rank_candidates`` pipeline, preserving cosine similarity in ``score`` so
``evaluations.run_eval --replay`` evaluates the exact ``0.60`` abstain policy.

Usage::

    py -3.12 -m scripts.rerank_eval_bench ^
        --dataset evaluations/datasets/retrieval_v4.json ^
        --out evaluations/reports/2026-11-24-v4-rerank-fixture.json
    py -3.12 -m evaluations.run_eval ^
        --dataset evaluations/datasets/retrieval_v4.json ^
        --replay evaluations/reports/2026-11-24-v4-rerank-fixture.json ^
        --k 5 ^
        --out evaluations/reports/2026-11-24-v4-rerank.md ^
        --json-out evaluations/reports/2026-11-24-v4-rerank.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from evaluations.dataset import EvalCase, EvalDataset, load_eval_dataset
from evaluations.metrics import (
    CaseResult,
    PassageKey,
    aggregate_metrics,
    macro_recall,
    recall_at_k,
    should_abstain,
)
from evaluations.run_eval import DEFAULT_ABSTAIN_THRESHOLD
from researchflow.knowledge.embeddings import (
    EMBEDDING_BATCH_SIZE,
    build_embeddings,
    embed_documents,
    embed_query,
)
from researchflow.knowledge.rerank import DEFAULT_RERANK_CANDIDATES, build_reranker


DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


def _load_env(path: Path) -> None:
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


def _embed_all_chunks(embeddings, texts: list[str], *, workers: int = 4) -> np.ndarray:
    batches = [
        texts[start : start + EMBEDDING_BATCH_SIZE]
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE)
    ]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda batch: embed_documents(embeddings, batch), batches))
    flat = [vector for batch in results for vector in batch]
    return np.asarray(flat, dtype=np.float32)


def _score_summary(
    dataset: EvalDataset,
    cases_by_id: dict[str, list[tuple[PassageKey, float]]],
    *,
    k: int,
) -> dict[str, float | int | None]:
    case_results: list[CaseResult] = []
    r1_values: list[float] = []
    r3_values: list[float] = []
    distractor_above_relevant = 0

    for case in dataset.cases:
        entries = cases_by_id[case.case_id][:k]
        ranked = tuple(key for key, _ in entries)
        scores = tuple(score for _, score in entries)
        case_results.append(
            CaseResult(
                case_id=case.case_id,
                project_key=case.project_key,
                difficulty=case.difficulty,
                relevant=case.relevant_keys,
                distractors=case.distractor_keys,
                ranked=ranked,
                scores=scores,
                latency_ms=None,
                abstained=should_abstain(scores, DEFAULT_ABSTAIN_THRESHOLD),
                cross_lingual=case.is_cross_lingual,
                multi_hop=case.is_multi_hop,
                k=k,
            )
        )
        if case.relevant_keys:
            rel = set(case.relevant_keys)
            r1_values.append(recall_at_k(rel, ranked, 1))
            r3_values.append(recall_at_k(rel, ranked, 3))
            if case.distractor_keys:
                dist = set(case.distractor_keys)
                first_dist = next(
                    (idx for idx, key in enumerate(ranked) if key in dist), None
                )
                first_rel = next(
                    (idx for idx, key in enumerate(ranked) if key in rel), None
                )
                if first_dist is not None and (
                    first_rel is None or first_dist < first_rel
                ):
                    distractor_above_relevant += 1

    agg = aggregate_metrics(case_results)
    return {
        "r@1": round(macro_recall(r1_values), 4),
        "r@3": round(macro_recall(r3_values), 4),
        "r@5": round(agg.macro_recall or 0.0, 4),
        "mrr": round(agg.mrr or 0.0, 4),
        "ndcg@5": round(agg.ndcg or 0.0, 4),
        "hard_neg_hit_rate": round(agg.hard_negative_hit_rate or 0.0, 4),
        "distractor_above_rel": distractor_above_relevant,
        "cross_lingual_r@5": round(agg.cross_lingual_recall or 0.0, 4),
        "unanswerable_abstain": round(agg.unanswerable_abstain_rate or 0.0, 4),
        "false_abstain": round(agg.false_abstain_rate or 0.0, 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--candidates", type=int, default=DEFAULT_RERANK_CANDIDATES)
    parser.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    args = parser.parse_args(argv)

    _load_env(args.env_file)
    os.environ.setdefault(
        "RESEARCHFLOW_DATABASE_URL",
        "postgresql+psycopg://researchflow:researchflow_dev_only@127.0.0.1:5432/researchflow",
    )
    os.environ["RESEARCHFLOW_RERANK_MODEL"] = args.rerank_model

    from researchflow.knowledge.retrieval import rank_candidates

    dataset, digest = load_eval_dataset(args.dataset)
    embeddings = build_embeddings()
    reranker = build_reranker()
    assert reranker is not None

    started = time.time()
    cases = list(dataset.cases)
    needed_projects = sorted({case.project_key for case in cases})

    hybrid_only_map: dict[str, list[tuple[PassageKey, float]]] = {}
    reranked_map: dict[str, list[tuple[PassageKey, float]]] = {}
    rerank_latencies_ms: list[float] = []

    for project_key in needed_projects:
        project = dataset.project(project_key)
        assert project is not None

        passages: list[PassageKey] = []
        texts: list[str] = []
        for document in project.documents:
            for index, chunk in enumerate(document.chunks):
                passages.append((document.document_key, index))
                texts.append(chunk)

        project_cases: list[EvalCase] = [
            item for item in cases if item.project_key == project_key
        ]
        t0 = time.time()
        vectors = _embed_all_chunks(embeddings, texts)
        matrix = _normalised(vectors)
        with ThreadPoolExecutor(max_workers=6) as pool:
            query_vectors = list(
                pool.map(lambda item: embed_query(embeddings, item.query), project_cases)
            )
        print(
            f"{project_key}: embedded {len(texts)} chunks + {len(project_cases)} queries "
            f"in {time.time() - t0:.1f}s",
            flush=True,
        )

        for case, q_vec_raw in zip(project_cases, query_vectors):
            q_vec = np.asarray(q_vec_raw, dtype=np.float32)
            norm = float(np.linalg.norm(q_vec)) or 1.0
            cosines = matrix @ (q_vec / norm)
            # Match SQL ORDER BY distance ASC, tie-breaking deterministically by passage order.
            cosine_order = sorted(
                range(len(texts)), key=lambda idx: (-float(cosines[idx]), idx)
            )
            ordered_texts = [texts[idx] for idx in cosine_order]
            ordered_passages = [passages[idx] for idx in cosine_order]
            ordered_cosines = [float(cosines[idx]) for idx in cosine_order]

            hybrid_selected = rank_candidates(
                case.query,
                ordered_texts,
                limit=args.k,
                use_lexical=True,
                reranker=None,
            )
            hybrid_only_map[case.case_id] = [
                (ordered_passages[pos], round(ordered_cosines[pos], 6))
                for pos in hybrid_selected
            ]

            r_start = time.perf_counter()
            rerank_selected = rank_candidates(
                case.query,
                ordered_texts,
                limit=args.k,
                use_lexical=True,
                reranker=reranker,
                rerank_candidates=args.candidates,
            )
            rerank_latencies_ms.append((time.perf_counter() - r_start) * 1000.0)
            reranked_map[case.case_id] = [
                (ordered_passages[pos], round(ordered_cosines[pos], 6))
                for pos in rerank_selected
            ]

    note = (
        f"Offline hybrid (bge-m3 cosine + CJK/Latin BM25 RRF top-{args.candidates}) "
        f"reordered by {args.rerank_model} via HttpReranker; score retains original "
        f"bge-m3 cosine similarity for 0.60 abstention calibration."
    )
    fixture = {
        "schema_version": 1,
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": digest,
        "k": args.k,
        "note": note,
        "cases": [
            {
                "case_id": case.case_id,
                "ranked_passages": [
                    {
                        "document_key": doc_key,
                        "chunk_index": chunk_idx,
                        "score": score,
                    }
                    for (doc_key, chunk_idx), score in reranked_map[case.case_id]
                ],
            }
            for case in cases
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    hybrid_summary = _score_summary(dataset, hybrid_only_map, k=args.k)
    rerank_summary = _score_summary(dataset, reranked_map, k=args.k)
    ordered_lat = sorted(rerank_latencies_ms)
    p50_ms = ordered_lat[len(ordered_lat) // 2] if ordered_lat else 0.0
    p95_ms = ordered_lat[int(len(ordered_lat) * 0.95)] if ordered_lat else 0.0

    print("\n=== Comparison on", dataset.dataset_version, "===")
    print("Hybrid RRF (no rerank):", json.dumps(hybrid_summary))
    print(f"Hybrid RRF + {args.rerank_model} (top-{args.candidates}->top-{args.k}):", json.dumps(rerank_summary))
    print(
        f"Rerank step latency (HTTP /rerank + BM25/RRF): p50={p50_ms:.1f}ms, p95={p95_ms:.1f}ms"
    )
    print(f"Wrote {args.out} in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
