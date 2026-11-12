"""Would a context window recover the cases that miss today?

The retrieval metric counts an exact chunk hit. A parent-document or sentence
window changes what the *agent* sees: a hit brings its neighbours with it. That
cannot change the retrieval metric, but it can change whether the answer is
available to the writer.

This measures the ceiling: for each answerable case and each cutoff, does any
labelled relevant passage fall inside the window around a returned hit? It reads
only a saved run and the dataset, so it needs no model and no database.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "evaluations/reports/2026-11-11-v4-hybrid-rescored.json",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "evaluations/datasets/retrieval_v4.json",
    )
    parser.add_argument("--radii", default="1,2,3")
    args = parser.parse_args(argv)

    radii = [int(part) for part in args.radii.split(",") if part.strip()]
    report = json.loads(args.report.read_text(encoding="utf-8"))
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))

    # chunk counts per (project, document), so a window can be clamped
    from researchflow.knowledge.chunking import chunk_markdown

    sizes: dict[tuple[str, str], int] = {}
    for project in dataset["projects"]:
        for document in project["documents"]:
            sizes[(project["project_key"], document["document_key"])] = len(
                chunk_markdown(document["content"])
            )

    answerable = [
        case
        for case in report["cases"]
        if case.get("relevant")
    ]
    total = len(answerable)
    print(f"answerable cases: {total}")
    print()
    header = f"{'window':>8} " + " ".join(f"{'k=' + str(k):>8}" for k in (1, 3, 5))
    print(header)

    def window_contains(hit, relevant, radius):
        document_key, chunk_index = hit
        project_key = next(
            case["project_key"]
            for case in answerable
            if hit in [tuple(item) for item in case["ranked"]]
        )
        count = sizes[(project_key, document_key)]
        low = max(0, chunk_index - radius)
        high = min(count - 1, chunk_index + radius)
        for rel_document, rel_index in relevant:
            if rel_document == document_key and low <= rel_index <= high:
                return True
        return False

    # Precompute each case's project key once; the hit lookup above is O(n).
    project_of = {
        case["case_id"]: case["project_key"] for case in report["cases"]
    }
    case_rows = []
    for case in answerable:
        case_rows.append(
            {
                "project_key": case["project_key"],
                "relevant": [tuple(item) for item in case["relevant"]],
                "ranked": [tuple(item) for item in case["ranked"]],
            }
        )

    for radius in (0, *radii):
        cells = []
        for k in (1, 3, 5):
            covered = 0
            for row in case_rows:
                hit_any = False
                for hit in row["ranked"][:k]:
                    document_key, chunk_index = hit
                    count = sizes[(row["project_key"], document_key)]
                    low = max(0, chunk_index - radius)
                    high = min(count - 1, chunk_index + radius)
                    if any(
                        rel_doc == document_key and low <= rel_index <= high
                        for rel_doc, rel_index in row["relevant"]
                    ):
                        hit_any = True
                        break
                covered += 1 if hit_any else 0
            cells.append(covered / total)
        label = "exact" if radius == 0 else f"±{radius}"
        print(f"{label:>8} " + " ".join(f"{value:>8.3f}" for value in cells))

    print()
    print("A cell is the share of answerable cases with at least one relevant")
    print("passage inside the window around one of the returned hits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
