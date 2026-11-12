"""Print fact-bearing candidate chunks for authoring retrieval-v4 cases.

Usage::

    py -3.12 -m scripts.dump_eval_candidates data-visualisation
    py -3.12 -m scripts.dump_eval_candidates markdown-pipeline 4 5

Second argument = how many candidates per volume, third = how many to print per
candidate list. Output is chunk_index plus the chunk text, so an anchor can be
copied verbatim.
"""

from __future__ import annotations

import argparse
import re
import sys

from scripts.build_eval_corpus import DEFAULT_NODE_MODULES, build_dataset
from researchflow.knowledge.chunking import chunk_markdown

FACT_MARKERS = re.compile(
    r"(\bdefault\b|\bmust\b|\bshould\b|\brequires?\b|\breturns?\b|\bsupports?\b|"
    r"\bversion\b|\d+\s*(ms|kb|mb|bytes|chars|seconds|%)|\bonly\b|\bnever\b|"
    r"\binstead of\b|\bnot supported\b|\bdeprecated\b)",
    re.IGNORECASE,
)


def candidates(text: str, *, limit: int) -> list[tuple[int, str]]:
    scored: list[tuple[int, int, str]] = []
    for chunk in chunk_markdown(text):
        body = chunk.content
        if not 350 <= len(body) <= 1500:
            continue
        score = len(FACT_MARKERS.findall(body))
        if score < 3:
            continue
        scored.append((score, chunk.chunk_index, body))

    scored.sort(key=lambda item: (-item[0], item[1]))

    picked: list[tuple[int, str]] = []
    for _score, index, body in scored:
        if len(picked) >= limit:
            break
        picked.append((index, body))
    return sorted(picked)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_key")
    parser.add_argument("--per-volume", type=int, default=3)
    parser.add_argument("--show", type=int, default=2)
    args = parser.parse_args(argv)

    dataset, _ = build_dataset(DEFAULT_NODE_MODULES)
    project = next(
        (item for item in dataset["projects"] if item["project_key"] == args.project_key),
        None,
    )
    if project is None:
        print(
            "unknown project; available: "
            + ", ".join(item["project_key"] for item in dataset["projects"]),
            file=sys.stderr,
        )
        return 2

    for document in project["documents"]:
        chunks = chunk_markdown(document["content"])
        picks = candidates(document["content"], limit=args.per_volume)
        for index, body in picks[: args.show]:
            print(
                f"\n--- {document['document_key']}  chunk_index={index} "
                f"(of {len(chunks)}) ---"
            )
            print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
