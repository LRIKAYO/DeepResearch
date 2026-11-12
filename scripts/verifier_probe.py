"""Measure the citation verifier against deliberately mismatched pairs.

The verifier is the component that decides whether a citation actually supports
its claim. Its unit tests use synthetic verdicts, so they prove the plumbing, not
the judgement. This probe builds pairs with known ground truth — five genuinely
supported, five deliberately mismatched — sends them to the real model through
the real verifier, and reports how many it gets right.

Usage::

    py -3.12 -m scripts.verifier_probe
    py -3.12 -m scripts.verifier_probe --out evaluations/reports/verifier-probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# (claim, passage, ground truth)
CASES: list[tuple[str, str, str]] = [
    (
        "The arc generator keeps three decimal places by default.",
        "arc.digits([digits]) - If digits is specified, sets the maximum number of "
        "digits after the decimal separator and returns this arc generator. If digits "
        "is not specified, returns the current maximum fraction digits, which defaults to 3.",
        "full",
    ),
    (
        "p-queue timeouts only start counting once the task leaves the backlog.",
        "The timeout for a task starts when the task is added to the queue, not when it "
        "starts running, so waiting time is included.",
        "none",
    ),
    (
        "fast-glob supports matching a basename with baseNameMatch.",
        "baseNameMatch: If true, then patterns without slashes will be matched against the "
        "basename of the path. Useful for matching files in subdirectories. Default: false.",
        "full",
    ),
    (
        "lru-cache purges expired entries on its own.",
        "maxAge is a convenient option which counts as both ttl and ttlAutopurge. If you set "
        "maxAge, then expired entries are removed automatically on a timer.",
        "full",
    ),
    (
        "Chunking splits Markdown on ATX headings.",
        "The project uses pgvector with a 1024-dimensional bge-m3 embedding and exact cosine "
        "distance; there is no approximate index.",
        "none",
    ),
    (
        "The Product Backend exposes a delete endpoint for projects.",
        "DELETE /projects/{project_id} deletes the Project and everything scoped to it: its "
        "Documents, their Chunks, and its Research Sessions.",
        "full",
    ),
    (
        "The OpenAI Node client retries all 4xx responses by default.",
        "The client retries on 408, 409, 429 and any 5xx response, up to two times by default. "
        "Other 4xx responses are not retried.",
        "none",
    ),
    (
        "semver coerce with rtl turns 1.2.3.4 into 2.3.4.",
        "coerce('1.2.3.4') will return 2.3.4 in rtl mode instead of 1.2.3 in ltr mode.",
        "full",
    ),
    (
        "espree parses as the latest ECMAScript edition when ecmaVersion is omitted.",
        "ecmaVersion - Set to 3, 5 (default), 6, 7, 8, 9, 10, 11, or 12 to specify the version "
        "of ECMAScript to parse.",
        "none",
    ),
    (
        "The research loop is bounded by a tool-round budget.",
        "RESEARCHFLOW_MAX_TOOL_ROUNDS caps how many tool rounds the loop may take before the "
        "writer runs; the value must be between 1 and 10.",
        "full",
    ),
]


def load_env(path: Path) -> None:
    import os

    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    load_env(args.env_file)

    from researchflow.agent.runtime import create_model, create_verifier

    verifier = create_verifier(create_model())
    items = [
        {
            "citation_id": f"c{index}",
            "claim": claim,
            "source": "probe",
            "passage": passage,
        }
        for index, (claim, passage, _truth) in enumerate(CASES, start=1)
    ]

    raw = verifier.invoke({"items": items})
    results = getattr(raw, "results", None) or []
    by_id = {result.citation_id: result for result in results}

    rows = []
    correct = 0
    strict_correct = 0
    for index, (claim, passage, truth) in enumerate(CASES, start=1):
        verdict = by_id.get(f"c{index}")
        support = verdict.support if verdict else "missing"
        # A mismatched pair is caught by any non-"full" verdict; a supported pair
        # is only fully correct when the verifier says "full".
        if truth == "none":
            ok = support in {"none", "partial"}
            strict = support == "none"
        else:
            ok = support == "full"
            strict = support == "full"
        correct += 1 if ok else 0
        strict_correct += 1 if strict else 0
        rows.append(
            {
                "citation_id": f"c{index}",
                "expected": truth,
                "verdict": support,
                "correct": ok,
                "reason": verdict.reason if verdict else "",
                "claim": claim,
            }
        )

    print(f"cases: {len(CASES)}")
    print(f"correct: {correct}/{len(CASES)}")
    print(f"strict (expected none must be 'none'): {strict_correct}/{len(CASES)}")
    for row in rows:
        print(
            f"  {row['citation_id']:<4} expected={row['expected']:<6} "
            f"got={row['verdict']:<8} {'OK ' if row['correct'] else 'MISS'} {row['claim'][:60]}"
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "cases": rows,
                    "correct": correct,
                    "strict_correct": strict_correct,
                    "total": len(CASES),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print("wrote", args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
