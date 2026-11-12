"""Validate retrieval-v4 case files against the compiled corpus, before merging.

For every case it checks that the Project exists, that every referenced chunk
index is inside its volume, and that the declared anchor occurs verbatim in that
chunk. It also reports the composition counts the dataset contract expects.

Usage::

    py -3.12 -m scripts.check_v4_cases evaluations/datasets/_v4_cases/*.json
"""

from __future__ import annotations

import argparse
import re
import json
import sys
from collections import Counter
from pathlib import Path

from scripts.build_eval_corpus import DEFAULT_NODE_MODULES, build_dataset
from researchflow.knowledge.chunking import chunk_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)

    dataset, _ = build_dataset(DEFAULT_NODE_MODULES)
    chunk_index: dict[tuple[str, str], list[str]] = {}
    for project in dataset["projects"]:
        for document in project["documents"]:
            texts = [chunk.content for chunk in chunk_markdown(document["content"])]
            chunk_index[(project["project_key"], document["document_key"])] = texts

    projects = {project["project_key"] for project in dataset["projects"]}

    cases: list[dict] = []
    for path in args.files:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list):
            print(f"{path}: expected a JSON array of cases", file=sys.stderr)
            return 2
        cases.extend(payload)

    failures: list[str] = []
    for case in cases:
        case_id = case.get("case_id", "<missing>")
        project_key = case.get("project_key")
        if project_key not in projects:
            failures.append(f"{case_id}: unknown project_key {project_key!r}")
            continue
        passages = list(case.get("relevant_passages") or []) + list(
            case.get("distractor_passages") or []
        )
        for passage in passages:
            document_key = passage.get("document_key")
            index = passage.get("chunk_index")
            anchor = passage.get("anchor")
            texts = chunk_index.get((project_key, document_key))
            if texts is None:
                failures.append(f"{case_id}: unknown document_key {document_key!r}")
                continue
            if not isinstance(index, int) or not 0 <= index < len(texts):
                failures.append(
                    f"{case_id}: chunk_index {index!r} out of range for "
                    f"{document_key} (0..{len(texts) - 1})"
                )
                continue
            if not isinstance(anchor, str) or anchor not in texts[index]:
                failures.append(
                    f"{case_id}: anchor not found verbatim in "
                    f"{document_key}#{index}: {anchor!r}"
                )

    ids = [case.get("case_id") for case in cases]
    duplicates = [key for key, count in Counter(ids).items() if count > 1]

    print(f"cases: {len(cases)}")
    print("by project:", dict(Counter(case.get("project_key") for case in cases)))
    print("difficulty:", dict(Counter(case.get("difficulty") for case in cases)))
    print(
        "answerable:",
        sum(1 for case in cases if case.get("relevant_passages")),
        "| unanswerable:",
        sum(1 for case in cases if not case.get("relevant_passages")),
    )
    print(
        "with distractors:",
        sum(1 for case in cases if case.get("distractor_passages")),
    )
    # Both flags are derived, exactly as evaluations/dataset.py derives them:
    # a CJK query is cross-lingual, and two relevant passages in different
    # volumes make a case multi-hop. They are not fields in the schema.
    cjk = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
    print(
        "cross-lingual (CJK query):",
        sum(1 for case in cases if cjk.search(case.get("query") or "")),
        "| multi-hop (2+ volumes):",
        sum(
            1
            for case in cases
            if len({p.get("document_key") for p in case.get("relevant_passages") or []}) >= 2
        ),
    )
    if duplicates:
        print("duplicate case_id:", duplicates)
    if failures:
        print()
        for failure in failures:
            print("FAIL", failure)
        return 1
    print("OK: every anchor matches its chunk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
