"""Rank-sensitivity analysis for a saved retrieval evaluation run.

A single ``Recall@5`` hides almost everything. When a Project corpus holds only
~20 chunks, returning 5 of them already covers a quarter of the corpus, so
Recall@5 saturates and stops distinguishing a good change from a bad one.

This module re-reads a completed run (the JSON written by ``run_eval``) and
reports the same cases at several cutoffs, plus the failure mode that actually
matters for RAG: how often a declared distractor enters the returned window, and
whether it ever outranks every relevant passage.

Offline and deterministic: it never calls a model, a database or the network.
"""

from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

Passage = tuple[str, int]

DEFAULT_KS: tuple[int, ...] = (1, 3, 5)


@dataclass(frozen=True)
class CutoffMetrics:
    k: int
    macro_recall: float
    micro_recall: float
    mrr: float
    distractor_hit_rate: float
    distractor_hit_cases: int
    distractor_cases: int
    distractor_above_relevant: int


@dataclass(frozen=True)
class Analysis:
    run_mode: str
    dataset_version: str
    run_id: str
    answerable_cases: int
    total_cases: int
    cutoffs: tuple[CutoffMetrics, ...]
    median_top1_score: float | None
    median_top1_margin: float | None
    coverage: tuple[tuple[str, int, float], ...]
    abstained_rate: float


def _passage(value: Any) -> Passage:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"not a passage reference: {value!r}")
    document_key, chunk_index = value
    if not isinstance(document_key, str) or not document_key:
        raise ValueError(f"invalid document key: {value!r}")
    return document_key, int(chunk_index)


def _passages(values: Iterable[Any]) -> set[Passage]:
    return {_passage(value) for value in values}


def _first_hit(ranked: Sequence[Passage], wanted: set[Passage]) -> int | None:
    for position, passage in enumerate(ranked, start=1):
        if passage in wanted:
            return position
    return None


def analyse(
    report: dict[str, Any],
    *,
    ks: Sequence[int] = DEFAULT_KS,
    corpus_chunks: dict[str, int] | None = None,
) -> Analysis:
    """Compute rank-sensitive metrics over one completed run."""

    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("report contains no cases")

    answerable = [case for case in cases if case.get("relevant")]

    cutoffs: list[CutoffMetrics] = []

    for k in ks:
        if k < 1:
            raise ValueError("cutoffs must be >= 1")

        recalls: list[float] = []
        micro_hits = 0
        micro_total = 0
        reciprocal_ranks: list[float] = []
        hit_cases = 0
        distractor_cases = 0
        above = 0

        for case in answerable:
            relevant = _passages(case["relevant"])
            distractors = _passages(case.get("distractors") or [])
            ranked = [_passage(item) for item in case.get("ranked") or []]

            window = set(ranked[:k])
            hits = len(relevant & window)
            recalls.append(hits / len(relevant))
            micro_hits += hits
            micro_total += len(relevant)

            position = _first_hit(ranked, relevant)
            reciprocal_ranks.append(1 / position if position else 0.0)

            if distractors:
                distractor_cases += 1
                if distractors & window:
                    hit_cases += 1
                first_relevant = _first_hit(ranked, relevant)
                first_distractor = _first_hit(ranked, distractors)
                if (
                    first_distractor is not None
                    and (first_relevant is None or first_distractor < first_relevant)
                ):
                    above += 1

        cutoffs.append(
            CutoffMetrics(
                k=k,
                macro_recall=statistics.fmean(recalls) if recalls else 0.0,
                micro_recall=(micro_hits / micro_total) if micro_total else 0.0,
                mrr=statistics.fmean(reciprocal_ranks) if reciprocal_ranks else 0.0,
                distractor_hit_rate=(
                    hit_cases / distractor_cases if distractor_cases else 0.0
                ),
                distractor_hit_cases=hit_cases,
                distractor_cases=distractor_cases,
                distractor_above_relevant=above,
            )
        )

    top_scores: list[float] = []
    margins: list[float] = []
    for case in answerable:
        scores = case.get("scores") or []
        if not scores:
            continue
        top_scores.append(float(scores[0]))
        if len(scores) > 1:
            margins.append(float(scores[0]) - float(scores[1]))

    coverage: list[tuple[str, int, float]] = []
    if corpus_chunks:
        largest_k = max(ks)
        for project_key, chunks in sorted(corpus_chunks.items()):
            if chunks > 0:
                coverage.append((project_key, chunks, largest_k / chunks))

    abstained = sum(1 for case in cases if case.get("abstained"))

    return Analysis(
        run_mode=str(report.get("mode") or "unknown"),
        dataset_version=str(report.get("dataset_version") or "unknown"),
        run_id=str(report.get("run_id") or "unknown"),
        answerable_cases=len(answerable),
        total_cases=len(cases),
        cutoffs=tuple(cutoffs),
        median_top1_score=statistics.median(top_scores) if top_scores else None,
        median_top1_margin=statistics.median(margins) if margins else None,
        coverage=tuple(coverage),
        abstained_rate=abstained / len(cases),
    )


def _reading(analysis: Analysis) -> list[str]:
    """Rule-based interpretation, so the document never needs hand editing."""

    notes: list[str] = []
    first = analysis.cutoffs[0]
    last = analysis.cutoffs[-1]

    if analysis.coverage:
        worst_share = max(share for _, _, share in analysis.coverage)
        if worst_share >= 0.15:
            notes.append(
                f"- The largest cutoff covers **{worst_share:.0%} of the whole "
                "Project corpus**. Recall at that cutoff saturates for "
                "geometric reasons, not retrieval quality: report a smaller "
                "cutoff as the headline, or grow the corpus."
            )

    if first.macro_recall < 0.95:
        missed = round((1 - first.macro_recall) * analysis.answerable_cases)
        notes.append(
            f"- Recall@1 is {first.macro_recall:.3f}: about {missed} answerable "
            "case(s) put the right passage second or later, even though every "
            "one of them is recovered by k="
            f"{last.k}."
        )

    if last.distractor_above_relevant == 0:
        notes.append(
            "- No case ranks a distractor above every relevant passage, so the "
            "failures are **tail contamination**, not wrong-answer-wins. That is "
            "the cheaper failure to fix: rerank or trim the window."
        )

    if last.distractor_cases and last.distractor_hit_rate >= 0.5:
        notes.append(
            f"- {last.distractor_hit_cases} of {last.distractor_cases} distractor "
            f"cases ({last.distractor_hit_rate:.0%}) return a declared distractor "
            f"within top-{last.k}. At k={first.k} the same rate is "
            f"{first.distractor_hit_rate:.0%}, which is the number a reader should "
            "treat as the retrieval hard-failure rate."
        )

    if analysis.abstained_rate > 0.2:
        notes.append(
            f"- The policy abstained on {analysis.abstained_rate:.0%} of all cases "
            f"({analysis.answerable_cases} answerable of {analysis.total_cases}); "
            "the threshold is a policy choice and needs calibration on a "
            "development split before any release claim."
        )

    return notes


def render_markdown(analysis: Analysis, *, source: "Path | str") -> str:
    lines: list[str] = []
    add = lines.append

    add("# Rank-sensitivity analysis")
    add("")
    add(f"Source run: `{Path(source).as_posix()}`")
    add("")
    add(
        f"Mode `{analysis.run_mode}` · dataset `{analysis.dataset_version}` · "
        f"run `{analysis.run_id}` · {analysis.answerable_cases} answerable of "
        f"{analysis.total_cases} cases"
    )
    add("")
    add("## Cutoff sensitivity")
    add("")
    add(
        "| k | Macro Recall@k | Micro Recall@k | MRR | Distractor in window | "
        "Distractor above every relevant |"
    )
    add("| --- | --- | --- | --- | --- | --- |")
    for item in analysis.cutoffs:
        add(
            f"| {item.k} | {item.macro_recall:.3f} | {item.micro_recall:.3f} | "
            f"{item.mrr:.3f} | {item.distractor_hit_cases}/{item.distractor_cases} "
            f"({item.distractor_hit_rate:.0%}) | {item.distractor_above_relevant} |"
        )
    add("")

    if analysis.coverage:
        add("## Corpus coverage")
        add("")
        add("| Project | Chunks | Largest k as a share of the corpus |")
        add("| --- | --- | --- |")
        for project_key, chunks, share in analysis.coverage:
            add(f"| {project_key} | {chunks} | {share:.0%} |")
        add("")

    add("## Separation")
    add("")
    if analysis.median_top1_score is not None:
        add(f"- Median top-1 score: {analysis.median_top1_score:.3f}")
    if analysis.median_top1_margin is not None:
        add(f"- Median top-1 minus top-2 margin: {analysis.median_top1_margin:.3f}")
    add(f"- Abstained rate: {analysis.abstained_rate:.0%}")
    add("")

    reading = _reading(analysis)
    if reading:
        add("## Reading")
        add("")
        lines.extend(reading)
        add("")

    return "\n".join(lines)


def _corpus_sizes(dataset_path: Path) -> tuple[dict[str, int], str | None]:
    from researchflow.knowledge.chunking import chunk_markdown

    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    sizes: dict[str, int] = {}
    for project in raw.get("projects") or []:
        key = project.get("project_key")
        if not isinstance(key, str):
            continue
        total = 0
        for document in project.get("documents") or []:
            content = document.get("content")
            if isinstance(content, str):
                total += len(chunk_markdown(content))
        sizes[key] = total

    version = raw.get("dataset_version")
    return sizes, version if isinstance(version, str) else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-read a saved retrieval run and report Recall@k, MRR, distractor "
            "exposure and corpus coverage. Offline; never calls a model or API."
        )
    )
    parser.add_argument("--report", required=True, type=Path, help="run JSON")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="optional dataset JSON, used to report corpus coverage",
    )
    parser.add_argument(
        "--ks",
        default=",".join(str(k) for k in DEFAULT_KS),
        help="comma-separated cutoffs (default: 1,3,5)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write markdown here")
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help=(
            "permit a --dataset whose version differs from the run's. Only for "
            "deliberate compatibility replays: coverage and the Reading section "
            "would otherwise describe a corpus the run never searched."
        ),
    )
    args = parser.parse_args(argv)

    ks = tuple(int(part) for part in args.ks.split(",") if part.strip())
    report = json.loads(args.report.read_text(encoding="utf-8"))

    corpus = None
    if args.dataset:
        corpus, dataset_version = _corpus_sizes(args.dataset)
        report_version = report.get("dataset_version")
        if (
            not args.allow_version_mismatch
            and isinstance(report_version, str)
            and dataset_version
            and report_version != dataset_version
        ):
            raise SystemExit(
                f"dataset version mismatch: the run is '{report_version}' but "
                f"--dataset is '{dataset_version}'. Coverage would describe a "
                "corpus that run never searched. Pair the run with its own "
                "dataset, or pass --allow-version-mismatch for a deliberate "
                "compatibility replay."
            )

    analysis = analyse(report, ks=ks, corpus_chunks=corpus)
    markdown = render_markdown(analysis, source=args.report)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
