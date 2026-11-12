"""Run a retrieval evaluation against the real Product Backend, or replay a frozen ranking.

Live mode (network + credentials required)::

    py -3.12 -m evaluations.run_eval \\
        --dataset evaluations/datasets/retrieval_v3.json \\
        --api http://127.0.0.1:8000 \\
        --user-id <uuid> \\
        --k 5 \\
        --out evaluations/reports/2026-11-10.md

Live mode creates one Project per dataset project, uploads every document through
``POST /projects/{project_id}/documents`` as ``multipart/form-data`` with a single
``file`` part, and calls ``POST /projects/{project_id}/knowledge/search`` for every
case. It uses only the public HTTP API: no direct database access and no backend
imports.

Replay mode (fully offline, no credentials)::

    py -3.12 -m evaluations.run_eval \\
        --dataset evaluations/datasets/retrieval_v3.json \\
        --replay evaluations/reports/ranking-fixture.json \\
        --k 5

Both modes compute the same retrieval metrics. Replay has no latency numbers because
there is no live request to time; the report says so instead of inventing a value.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from evaluations.dataset import (
    DEFAULT_DATASET,
    DatasetValidationError,
    EvalDataset,
    composition,
    load_eval_dataset,
)
from evaluations.metrics import (
    AggregateMetrics,
    CaseResult,
    aggregate_metrics,
    should_abstain,
)

DEFAULT_K = 5
DEFAULT_ABSTAIN_THRESHOLD = 0.60
DEFAULT_TIMEOUT_SECONDS = 60.0


class EvalError(RuntimeError):
    """A live or replay evaluation could not be completed."""


class ReplayFixtureError(EvalError):
    """The frozen ranking fixture is inconsistent with the dataset."""


# ---------------------------------------------------------------------------
# Replay fixture schema
# ---------------------------------------------------------------------------


class _RankingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class RankingHit(_RankingModel):
    document_key: str = Field(min_length=1, max_length=200)
    chunk_index: int = Field(ge=0)
    score: float | None = Field(default=None, ge=-1.0, le=1.0)


class CaseRanking(_RankingModel):
    case_id: str = Field(min_length=1)
    ranked_passages: list[RankingHit] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_passages(self):
        keys = [(hit.document_key, hit.chunk_index) for hit in self.ranked_passages]
        if len(keys) != len(set(keys)):
            raise ValueError("Ranking contains a duplicate passage")
        return self


class RankingFixture(_RankingModel):
    schema_version: Literal[1]
    dataset_version: str = Field(min_length=1)
    dataset_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    k: int | None = Field(default=None, ge=1)
    cases: list[CaseRanking]
    # Optional caveat carried by the fixture itself, so the disclaimer survives
    # regeneration instead of living only in a hand-edited report.
    note: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluations.run_eval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Compute retrieval metrics for a ResearchFlow dataset. Live mode ingests the\n"
            "corpus through the Product Backend HTTP API; replay mode reads frozen rankings\n"
            "and never touches the network."
        ),
        epilog=(
            "examples:\n"
            "  py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v3.json \\\n"
            "      --api http://127.0.0.1:8000 --user-id <uuid> --k 5 --out evaluations/reports/run.md\n"
            "  py -3.12 -m evaluations.run_eval --dataset evaluations/datasets/retrieval_v3.json \\\n"
            "      --replay ranking-fixture.json --k 5 --out evaluations/reports/replay.md\n"
            "  py -3.12 -m evaluations.run_eval --validate-only\n"
        ),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        metavar="PATH",
        help="dataset JSON (schema_version 1 or 2); default: evaluations/datasets/retrieval_v3.json",
    )
    parser.add_argument(
        "--api",
        metavar="URL",
        default=None,
        help="base URL of the running Product Backend (live mode); requires --user-id",
    )
    parser.add_argument(
        "--user-id",
        metavar="UUID",
        default=None,
        help="value for the X-ResearchFlow-User-Id header in live mode",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        metavar="RANKING_JSON",
        default=None,
        help="frozen ranking fixture; computes metrics with no network access",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K, metavar="INT", help="cutoff (default: 5)")
    parser.add_argument(
        "--abstain-threshold",
        type=float,
        default=DEFAULT_ABSTAIN_THRESHOLD,
        metavar="FLOAT",
        help=(
            "abstain when the top returned score is below this cosine similarity "
            f"(default: {DEFAULT_ABSTAIN_THRESHOLD:.2f}); requires calibration on a dev set"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="per-request HTTP timeout in live mode (default: 60)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        metavar="PATH",
        default=None,
        help="write the Markdown report here; when omitted the report goes to stdout",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        metavar="PATH",
        default=None,
        help="optional machine-readable metrics artifact",
    )
    parser.add_argument(
        "--cost-per-run",
        default=None,
        metavar="TEXT",
        help="operator-supplied cost figure for the report; not measured by this tool",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate the dataset and print its composition without evaluating",
    )
    return parser


def _validate_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.k < 1:
        parser.error("--k must be a positive integer")
    if args.k > 20:
        parser.error("--k must be at most 20 (Product Backend search limit)")
    if not 0.0 <= args.abstain_threshold <= 1.0:
        parser.error("--abstain-threshold must be between 0 and 1")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.api is not None and args.replay is not None:
        parser.error("--api and --replay are mutually exclusive")
    if args.replay is not None and args.user_id is not None:
        parser.error("--user-id is only valid with --api")
    if args.api is not None:
        parsed = urlparse(args.api)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            parser.error("--api must be an absolute http(s) URL")
        if args.user_id is None:
            parser.error("--api requires --user-id")
        try:
            UUID(args.user_id)
        except ValueError:
            parser.error("--user-id must be a valid UUID")
    if args.api is None and args.replay is None and not args.validate_only:
        parser.error("one of --api or --replay is required (or use --validate-only)")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_arguments(parser, args)

    try:
        dataset, dataset_sha256 = load_eval_dataset(args.dataset)
        if args.validate_only:
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "dataset_version": dataset.dataset_version,
                        "dataset_sha256": dataset_sha256,
                        "schema_version": dataset.schema_version,
                        "composition": composition(dataset).as_dict(),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if args.replay is not None:
            rankings = load_ranking_fixture(args.replay, dataset, dataset_sha256)
            results = run_replay(dataset, rankings, args.k, args.abstain_threshold)
            mode = "replay"
            api_label = None
            run_id = None
            provenance_note = rankings.note
        else:
            assert args.api is not None and args.user_id is not None
            results, run_id = run_live(
                dataset,
                api=args.api,
                user_id=args.user_id,
                k=args.k,
                abstain_threshold=args.abstain_threshold,
                timeout=args.timeout,
            )
            mode = "live"
            api_label = args.api
            provenance_note = None
    except DatasetValidationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ReplayFixtureError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except EvalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"error: live request failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    metrics = aggregate_metrics(results)
    report = render_report(
        dataset=dataset,
        dataset_path=args.dataset,
        dataset_sha256=dataset_sha256,
        mode=mode,
        api_label=api_label,
        run_id=run_id,
        k=args.k,
        abstain_threshold=args.abstain_threshold,
        results=results,
        metrics=metrics,
        generated_at=generated_at,
        cost_per_run=args.cost_per_run,
        provenance_note=provenance_note,
    )

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(report)

    if args.json_out is not None:
        artifact = {
            "mode": mode,
            "dataset_version": dataset.dataset_version,
            "dataset_sha256": dataset_sha256,
            "schema_version": dataset.schema_version,
            "k": args.k,
            "abstain_threshold": args.abstain_threshold,
            "generated_at_utc": generated_at,
            "api": api_label,
            "run_id": run_id,
            "cost_per_run": args.cost_per_run,
            "provenance_note": provenance_note,
            "composition": composition(dataset).as_dict(),
            "metrics": metrics.as_dict(),
            "cases": [asdict(result) for result in results],
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.json_out}")
    return 0


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


class RankingMap(dict[str, "CaseRanking"]):
    """case_id -> ranking, carrying the fixture's optional provenance note.

    A dict subclass so every existing caller and comparison keeps working; the
    note rides along so the disclaimer can be rendered into the report instead
    of being hand-edited into it.
    """

    def __init__(self, *args, note: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.note = note


def load_ranking_fixture(
    path: Path, dataset: EvalDataset, dataset_sha256: str
) -> RankingMap:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise ReplayFixtureError(f"{path}: cannot read ranking fixture: {error}") from None
    try:
        fixture = RankingFixture.model_validate_json(raw)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc']) or '<root>'}: {item['msg']}"
            for item in error.errors(include_url=False)
        )
        raise ReplayFixtureError(f"{path}: invalid ranking fixture: {details}") from None
    if fixture.dataset_version != dataset.dataset_version:
        raise ReplayFixtureError(
            f"{path}: fixture dataset_version {fixture.dataset_version!r} does not match "
            f"dataset {dataset.dataset_version!r}"
        )
    if fixture.dataset_sha256 is not None and fixture.dataset_sha256 != dataset_sha256:
        raise ReplayFixtureError(
            f"{path}: fixture dataset_sha256 does not match the dataset file"
        )

    by_id = {ranking.case_id: ranking for ranking in fixture.cases}
    if len(by_id) != len(fixture.cases):
        raise ReplayFixtureError(f"{path}: duplicate case_id in ranking fixture")
    expected = {case.case_id for case in dataset.cases}
    unknown = sorted(set(by_id) - expected)
    missing = sorted(expected - set(by_id))
    if unknown:
        raise ReplayFixtureError(f"{path}: ranking fixture has unknown case_id(s): {unknown[:5]}")
    if missing:
        raise ReplayFixtureError(f"{path}: ranking fixture is missing case_id(s): {missing[:5]}")

    for case in dataset.cases:
        project = dataset.project(case.project_key)
        assert project is not None  # guaranteed by dataset validation
        for hit in by_id[case.case_id].ranked_passages:
            document = project.document(hit.document_key)
            if document is None:
                raise ReplayFixtureError(
                    f"{path}: case {case.case_id!r} ranks unknown document_key "
                    f"{hit.document_key!r} in project {case.project_key!r}"
                )
            if hit.chunk_index >= len(document.chunks):
                raise ReplayFixtureError(
                    f"{path}: case {case.case_id!r} ranks missing chunk_index {hit.chunk_index} "
                    f"of {hit.document_key!r} (document has {len(document.chunks)} chunks)"
                )
    return RankingMap(by_id, note=fixture.note)


def run_replay(
    dataset: EvalDataset,
    rankings: dict[str, CaseRanking],
    k: int,
    abstain_threshold: float,
) -> list[CaseResult]:
    results = []
    for case in dataset.cases:
        hits = rankings[case.case_id].ranked_passages[:k]
        ranked = tuple((hit.document_key, hit.chunk_index) for hit in hits)
        scores = tuple(hit.score for hit in hits)
        results.append(
            CaseResult(
                case_id=case.case_id,
                project_key=case.project_key,
                difficulty=case.difficulty,
                relevant=case.relevant_keys,
                distractors=case.distractor_keys,
                ranked=ranked,
                scores=scores,
                latency_ms=None,
                abstained=should_abstain(scores, abstain_threshold),
                cross_lingual=case.is_cross_lingual,
                multi_hop=case.is_multi_hop,
                k=k,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Live API ingestion
# ---------------------------------------------------------------------------


@dataclass
class _IngestedProject:
    project_id: str
    document_ids: dict[str, str]


def run_live(
    dataset: EvalDataset,
    *,
    api: str,
    user_id: str,
    k: int,
    abstain_threshold: float,
    timeout: float,
) -> tuple[list[CaseResult], str]:
    """Create projects, upload documents, and search through the public API.

    The search hit does not expose ``chunk_index``, so hits are mapped back to
    logical passages with the stable ``(document_id, chunk content)`` pair that
    the backend returns. This avoids reading the database and makes an
    ingestion/chunking mismatch a loud failure instead of a silent mislabel.
    """
    run_id = uuid4().hex[:8]
    headers = {"X-ResearchFlow-User-Id": user_id}
    ingested: dict[str, _IngestedProject] = {}
    hit_map: dict[tuple[str, str, str], tuple[str, int]] = {}

    base_url = api.rstrip("/") + "/"
    # The Product Backend exposes no delete endpoint, so freshly created
    # projects stay in the target environment. The run_id in each project name
    # makes them easy to identify; use a disposable stack.
    with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
        for project in dataset.projects:
            response = client.post(
                "projects",
                json={"name": f"{dataset.dataset_version} {project.project_key} {run_id}"[:120]},
            )
            _expect(response, 201, f"Project creation for {project.project_key!r}")
            project_id = _json_field(response, "project_id")
            ingested[project.project_key] = _IngestedProject(project_id, {})

            for document in project.documents:
                response = client.post(
                    f"projects/{project_id}/documents",
                    files={
                        "file": (
                            document.filename,
                            document.content.encode("utf-8"),
                            "text/markdown",
                        )
                    },
                )
                _expect(
                    response,
                    201,
                    f"Document upload {document.document_key!r} for {project.project_key!r}",
                )
                document_id = _json_field(response, "document_id")
                ingested[project.project_key].document_ids[document.document_key] = document_id
                for chunk_index, chunk in enumerate(document.chunks):
                    key = (project.project_key, document_id, chunk)
                    if key in hit_map:
                        raise EvalError(
                            f"project {project.project_key!r} has two identical chunks; "
                            "search results cannot be mapped back to a chunk_index"
                        )
                    hit_map[key] = (document.document_key, chunk_index)

        results = []
        for case in dataset.cases:
            project_id = ingested[case.project_key].project_id
            started = monotonic()
            response = client.post(
                f"projects/{project_id}/knowledge/search",
                json={"query": case.query, "limit": k},
            )
            latency_ms = (monotonic() - started) * 1000.0
            _expect(response, 200, f"Knowledge search for case {case.case_id!r}")
            payload = _json_payload(response, f"Knowledge search for case {case.case_id!r}")
            if not isinstance(payload, list):
                raise EvalError(f"case {case.case_id!r}: search response was not a list")
            if len(payload) > k:
                raise EvalError(
                    f"case {case.case_id!r}: search returned {len(payload)} hits for limit {k}"
                )
            ranked: list[tuple[str, int]] = []
            scores: list[float] = []
            seen: set[tuple[str, int]] = set()
            for hit in payload:
                if not isinstance(hit, dict):
                    raise EvalError(f"case {case.case_id!r}: search hit was not a JSON object")
                try:
                    document_id = str(hit["document_id"])
                    content = str(hit["content"])
                    score = float(hit["score"])
                except (KeyError, TypeError, ValueError):
                    raise EvalError(
                        f"case {case.case_id!r}: search hit is missing document_id, "
                        "content, or score"
                    ) from None
                logical = hit_map.get((case.project_key, document_id, content))
                if logical is None:
                    known = {
                        chunk
                        for (project_key, known_document, chunk) in hit_map
                        if project_key == case.project_key
                        and known_document == document_id
                    }
                    sample = next(iter(known), "")
                    raise EvalError(
                        f"case {case.case_id!r}: search returned a chunk that was not "
                        "ingested from this dataset (content or document_id mismatch); "
                        f"document_id={document_id!r} chunks_known_for_document={len(known)} "
                        f"returned_len={len(content)} sample_known_len={len(sample)} "
                        f"returned_head={content[:80]!r}"
                    )
                if logical in seen:
                    raise EvalError(
                        f"case {case.case_id!r}: search returned the same chunk twice"
                    )
                seen.add(logical)
                ranked.append(logical)
                scores.append(score)
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    project_key=case.project_key,
                    difficulty=case.difficulty,
                    relevant=case.relevant_keys,
                    distractors=case.distractor_keys,
                    ranked=tuple(ranked),
                    scores=tuple(scores),
                    latency_ms=latency_ms,
                    abstained=should_abstain(tuple(scores), abstain_threshold),
                    cross_lingual=case.is_cross_lingual,
                    multi_hop=case.is_multi_hop,
                    k=k,
                )
            )
    return results, run_id


def _expect(response: httpx.Response, status: int, operation: str) -> None:
    if response.status_code != status:
        raise EvalError(f"{operation} failed with HTTP {response.status_code}")


def _json_payload(response: httpx.Response, operation: str):
    try:
        return response.json()
    except ValueError:
        raise EvalError(f"{operation} returned invalid JSON") from None


def _json_field(response: httpx.Response, field: str) -> str:
    payload = _json_payload(response, f"response for {field}")
    if not isinstance(payload, dict) or field not in payload:
        raise EvalError(f"response is missing the {field} field")
    return str(payload[field])


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _latency_cell(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f} ms"


def _case_flags(result: CaseResult) -> str:
    flags = []
    if result.is_unanswerable:
        flags.append("unans")
    if result.multi_hop:
        flags.append("multi")
    if result.cross_lingual:
        flags.append("xling")
    if result.distractors:
        flags.append("neg")
    return ", ".join(flags) if flags else "-"


def _abstain_cell(result: CaseResult) -> str:
    decision = "yes" if result.abstained else "no"
    mark = "ok" if result.abstain_correct else "WRONG"
    return f"{decision} ({mark})"


def _top1_cell(result: CaseResult) -> str:
    if result.top1 is None:
        return "-"
    return f"`{result.top1[0]}#{result.top1[1]}`"


def render_report(
    *,
    dataset: EvalDataset,
    dataset_path: Path,
    dataset_sha256: str,
    mode: str,
    api_label: str | None,
    run_id: str | None,
    k: int,
    abstain_threshold: float,
    results: list[CaseResult],
    metrics: AggregateMetrics,
    generated_at: str,
    cost_per_run: str | None,
    provenance_note: str | None = None,
) -> str:
    counts = composition(dataset)
    latency_count = sum(1 for result in results if result.latency_ms is not None)
    if mode == "replay":
        latency_note = "n/a (replay has no network requests to time)"
    elif latency_count == 0:
        latency_note = "n/a (no latency captured)"
    else:
        latency_note = f"{latency_count} measured searches"
    cost = cost_per_run if cost_per_run is not None else "TODO(needs-credentials)"
    lines = [f"# Retrieval Evaluation — {dataset.dataset_version}", ""]
    if provenance_note:
        lines.extend([f"> {provenance_note}", ""])
    lines.extend([
        "## Run metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Dataset | `{dataset.dataset_version}` (schema v{dataset.schema_version}) |",
        f"| Dataset SHA-256 | `{dataset_sha256}` |",
        f"| Mode | {mode} |",
        f"| API base URL | {api_label if api_label else 'n/a (replay)'} |",
        f"| Run id | {run_id if run_id else 'n/a (replay)'} |",
        f"| Cutoff k | {k} |",
        f"| Abstain threshold | {abstain_threshold:.2f} (cosine similarity) |",
        f"| Generated at (UTC) | {generated_at} |",
        f"| Cost per run | {cost} |",
        "",
        f"> Labels: {dataset.label_note}",
        "",
    ])
    lines.extend([
        "## Headline metrics",
        "",
        f"Macro, MRR, and nDCG are computed over the {metrics.answerable_count} answerable "
        f"cases. Unanswerable cases (n={metrics.unanswerable_count}) are scored through the "
        "abstain metrics instead.",
        "",
        "| Metric | Value | Denominator |",
        "| --- | --- | --- |",
        f"| Macro Recall@{k} | {_fmt(metrics.macro_recall)} | {metrics.answerable_count} answerable cases |",
        f"| Micro Recall@{k} | {_fmt(metrics.micro_recall)} | all relevant passages |",
        f"| MRR | {_fmt(metrics.mrr)} | {metrics.answerable_count} answerable cases |",
        f"| nDCG@{k} | {_fmt(metrics.ndcg)} | {metrics.answerable_count} answerable cases |",
        f"| Hard-negative hit rate (lower is better) | {_fmt(metrics.hard_negative_hit_rate)} | {metrics.hard_negative_case_count} cases with distractors |",
        f"| Cross-lingual Recall@{k} | {_fmt(metrics.cross_lingual_recall)} | {metrics.cross_lingual_case_count} answerable CJK-query cases |",
        f"| Unanswerable abstain rate | {_fmt(metrics.unanswerable_abstain_rate)} | {metrics.unanswerable_count} unanswerable cases |",
        f"| False-abstain rate (lower is better) | {_fmt(metrics.false_abstain_rate)} | {metrics.answerable_count} answerable cases |",
        f"| Abstain correctness | {_fmt(metrics.abstain_correctness)} | all {metrics.case_count} cases |",
        f"| Latency p50 | {_latency_cell(metrics.latency_p50_ms)} | {latency_note} |",
        f"| Latency p95 | {_latency_cell(metrics.latency_p95_ms)} | {latency_note} |",
        "",
        "## Dataset composition",
        "",
        "| Dimension | Count |",
        "| --- | --- |",
        f"| Projects | {counts.projects} |",
        f"| Documents | {counts.documents} |",
        f"| Chunks (re-chunked offline) | {counts.chunks} |",
        f"| Cases | {counts.cases} |",
        f"| Easy / medium / hard | {counts.easy} / {counts.medium} / {counts.hard} |",
        f"| Hard-negative cases | {counts.hard_negative} |",
        f"| Multi-hop cases | {counts.multi_hop} |",
        f"| Cross-lingual cases | {counts.cross_lingual} |",
        f"| Unanswerable cases | {counts.unanswerable} |",
        "",
        "## Per-case detail",
        "",
        "`RR` is the reciprocal rank of the first relevant passage. `HN hit` is whether a "
        "declared distractor entered the top-k (lower is better). `Abstain` shows the policy "
        "decision and whether it was correct for the case.",
        "",
        "| Case | Project | Difficulty | Flags | "
        f"Recall@{k} | RR | nDCG@{k} | HN hit | Abstain | Top-1 | Latency (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for result in results:
        hn_hit = result.hard_negative_hit
        hn_cell = "-" if hn_hit is None else ("yes" if hn_hit else "no")
        latency_cell = "-" if result.latency_ms is None else f"{result.latency_ms:.1f}"
        lines.append(
            f"| {result.case_id} | {result.project_key} | {result.difficulty} | "
            f"{_case_flags(result)} | "
            f"{_fmt(result.recall)} | {_fmt(result.reciprocal_rank)} | {_fmt(result.ndcg)} | "
            f"{hn_cell} | {_abstain_cell(result)} | {_top1_cell(result)} | {latency_cell} |"
        )
    lines.extend(
        [
            "",
            "## Method and limitations",
            "",
            "- Relevance is literal: a passage is labelled relevant only when its chunk text "
            "contains the answer. Every `(document_key, chunk_index, anchor)` tuple is checked "
            "against `researchflow.knowledge.chunking.chunk_markdown` before any request is made.",
            "- `Recall@k`, MRR, and nDCG use binary relevance. Macro Recall is the unweighted "
            "mean over answerable cases; Micro Recall pools relevant passages.",
            "- The hard-negative hit rate is a failure rate over cases with declared "
            "`distractor_passages`; lower is better. Unanswerable cases may also declare "
            "distractors, in which case returning one is a hard-negative hit.",
            "- Abstention is a retrieval-side proxy: the system abstains when no returned "
            "passage scores at least the configured threshold. The default threshold is a "
            "policy choice, not a calibrated probability; calibrate it on a development split "
            "before using abstain numbers for release decisions.",
            "- Latency percentiles use the nearest-rank method over measured search requests; "
            "replay runs have no latency and report `n/a` rather than a fabricated number.",
            "- Citation support rate and answer quality are not measured here. They require an "
            "agent-level evaluation with generated answers and a citation verifier.",
            "- Cost per run is not observable from the API; it is either operator-supplied or "
            "left as `TODO(needs-credentials)`.",
            "- Live mode creates projects and documents in the target backend and cannot delete "
            "them (the Product Backend has no delete endpoint). Run it against a disposable "
            "stack. Projects are named with the dataset version and a random run id.",
            "",
            "## Reproduction",
            "",
            "Live (needs a running backend, embedding credentials, and a disposable database):",
            "",
            "```powershell",
            "py -3.12 -m evaluations.run_eval "
            f"--dataset {dataset_path.as_posix()} "
            "--api http://127.0.0.1:8000 --user-id <uuid> "
            f"--k {k} --abstain-threshold {abstain_threshold:.2f} "
            "--out evaluations/reports/<date>.md",
            "```",
            "",
            "Replay (offline, no credentials):",
            "",
            "```powershell",
            "py -3.12 -m evaluations.run_eval "
            f"--dataset {dataset_path.as_posix()} "
            "--replay <ranking-fixture.json> "
            f"--k {k} --abstain-threshold {abstain_threshold:.2f} "
            "--out evaluations/reports/<date>-replay.md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
