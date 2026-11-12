"""Turn a saved run into a replay fixture, so it can be re-scored under today's policy.

A saved report is a snapshot: it records the ranking, the scores and the verdicts
that the policy produced at the time. When a policy changes — the abstain rule,
for instance — the honest way to compare an old run with a new one is to re-score
both under the current rule, not to compare a new number against an old one.

Usage::

    py -3.12 -m scripts.rescore_run `
      --report evaluations/reports/2026-11-11-v4-live.json `
      --out evaluations/reports/2026-11-11-v4-live-fixture.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--note", default=None)
    args = parser.parse_args(argv)

    report = json.loads(args.report.read_text(encoding="utf-8"))

    cases = []
    for case in report.get("cases") or []:
        ranked = case.get("ranked") or []
        scores = case.get("scores") or []
        if len(ranked) != len(scores):
            raise SystemExit(
                f"{case.get('case_id')}: {len(ranked)} ranked passages but "
                f"{len(scores)} scores"
            )
        cases.append(
            {
                "case_id": case["case_id"],
                "ranked_passages": [
                    {
                        "document_key": document_key,
                        "chunk_index": chunk_index,
                        "score": score,
                    }
                    for (document_key, chunk_index), score in zip(ranked, scores)
                ],
            }
        )

    note = args.note or (
        "Re-scored from a saved run: the stored ranking and cosine scores, "
        "re-evaluated under the current abstain policy. No new retrieval happened."
    )

    fixture = {
        "schema_version": 1,
        "dataset_version": report["dataset_version"],
        "dataset_sha256": report.get("dataset_sha256"),
        "k": report.get("k"),
        "note": note,
        "cases": cases,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(cases)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
