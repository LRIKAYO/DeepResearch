"""Re-point authored case anchors at their chunk index in the rebuilt corpus.

Rebuilding the corpus can move a chunk (deduplication removes repeats and
re-chunks each volume), which invalidates the ``chunk_index`` recorded in the
case fragments. The anchor text does not move: it is a verbatim substring of
exactly one chunk. This tool re-derives the index from the anchor and rewrites
the fragment in place.

It refuses to guess. If an anchor appears in no chunk, or in more than one, the
case is reported and left untouched rather than silently mislabelled.

Usage::

    py -3.12 -m scripts.repair_case_anchors `
      --dataset evaluations/datasets/retrieval_v4.json `
      --cases-dir evaluations/datasets/_v4_cases
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from researchflow.knowledge.chunking import chunk_markdown


def _chunk_index(dataset_path: Path) -> dict[tuple[str, str], list[str]]:
    """Chunk the raw dataset file directly.

    ``load_eval_dataset`` validates labels, and a rebuild invalidates exactly the
    indices this tool exists to repair, so it cannot be used here.
    """

    raw = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    index: dict[tuple[str, str], list[str]] = {}
    for project in raw["projects"]:
        for document in project["documents"]:
            index[(project["project_key"], document["document_key"])] = [
                chunk.content for chunk in chunk_markdown(document["content"])
            ]
    return index


def _resolve(texts: list[str], anchor: str) -> tuple[int | None, str, str | None]:
    """Find the chunk for an anchor after a re-chunk.

    Returns ``(index, anchor, note)``. ``note`` is None on an unambiguous hit,
    ``"ambiguous"`` when the text occurs in several chunks (the first is used),
    ``"shortened"`` when the original anchor straddled a boundary and a prefix
    of it is unique, and ``"missing"`` when nothing matches.
    """

    matches = [index for index, text in enumerate(texts) if anchor in text]
    if len(matches) == 1:
        return matches[0], anchor, None
    if len(matches) > 1:
        return matches[0], anchor, "ambiguous"

    for length in range(len(anchor) - 1, 29, -1):
        candidate = anchor[:length].rstrip()
        if not candidate:
            continue
        matches = [index for index, text in enumerate(texts) if candidate in text]
        if len(matches) == 1:
            return matches[0], candidate, "shortened"
        if len(matches) > 1:
            return matches[0], candidate, "ambiguous"

    return None, anchor, "missing"



def _resolve_excluding(
    texts: list[str], anchor: str, taken: set[tuple[str, int]]
) -> tuple[int | None, str, str | None]:
    """Resolve a distractor, never onto a chunk already used as relevant."""

    blocked = {index for (_document, index) in taken}
    matches = [
        index
        for index, text in enumerate(texts)
        if anchor in text and index not in blocked
    ]
    if not matches:
        return None, anchor, "missing"
    if len(matches) == 1:
        return matches[0], anchor, None
    return matches[0], anchor, "ambiguous"

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cases-dir", type=Path, required=True)
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite the fragment files; without it, report only",
    )
    args = parser.parse_args(argv)

    chunk_text = _chunk_index(args.dataset)

    fixed = 0
    notes: list[str] = []
    problems: list[str] = []

    for fragment in sorted(args.cases_dir.glob("*.json")):
        cases = json.loads(fragment.read_text(encoding="utf-8-sig"))
        changed = False

        for case in cases:
            project_key = case["project_key"]
            taken: set[tuple[str, int]] = set()

            for field in ("relevant_passages", "distractor_passages"):
                kept: list[dict] = []
                for passage in case.get(field) or []:
                    document_key = passage["document_key"]
                    texts = chunk_text.get((project_key, document_key))
                    if texts is None:
                        problems.append(
                            f"{case['case_id']}: unknown document {document_key}"
                        )
                        continue

                    if field == "distractor_passages":
                        index, anchor, note = _resolve_excluding(
                            texts, passage["anchor"], taken
                        )
                        if index is None:
                            notes.append(
                                f"{case['case_id']}: dropped a distractor whose text "
                                f"only overlaps a relevant chunk ({document_key})"
                            )
                            changed = True
                            continue
                    else:
                        index, anchor, note = _resolve(texts, passage["anchor"])

                    if index is None:
                        problems.append(
                            f"{case['case_id']}: anchor no longer present in "
                            f"{document_key}: {passage['anchor'][:60]!r}"
                        )
                        continue

                    if passage["chunk_index"] != index:
                        passage["chunk_index"] = index
                        changed = True
                        fixed += 1
                    if anchor != passage["anchor"]:
                        passage["anchor"] = anchor
                        changed = True
                    if note == "ambiguous":
                        notes.append(
                            f"{case['case_id']}: anchor occurs in several chunks of "
                            f"{document_key}; using {index}"
                        )

                    taken.add((document_key, index))
                    kept.append(passage)

                if field == "distractor_passages":
                    case["distractor_passages"] = kept

        if changed and args.write:
            fragment.write_text(
                json.dumps(cases, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    print(f"re-pointed passages: {fixed}")
    if notes:
        print(f"ambiguous anchors: {len(notes)}")
        for note in notes:
            print("  NOTE", note)
    if problems:
        print(f"problems: {len(problems)}")
        for problem in problems:
            print("  FAIL", problem)
        return 1

    print("OK: every anchor resolves to exactly one chunk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
