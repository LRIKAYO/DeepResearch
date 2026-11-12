"""Citation audit for a generated report.

A Writer pass routinely lists more sources than it actually cites: the evidence
inventory is built from every retrieved passage, so a report that cites four of
twenty-five passages still publishes twenty-five sources. The Verifier then
correctly reports twenty-one "listed but not cited" verdicts, which makes the
verification layer look like it is catching hallucinations when it is really
catching a formatting failure in the Writer.

This module makes that failure measurable and repairable: it counts which
citation ids the report body actually uses, so the runtime can attempt one
rewrite before the verifier runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CITATION_MARKER = re.compile(r"\[c([1-9][0-9]*)\]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?。！？;；])")

# Sentences that only structure the report do not need a marker.
_STRUCTURAL = re.compile(
    r"^\s*(#|[-*+]\s*$|\d+\.\s*$|```|\||>)", re.MULTILINE
)


@dataclass(frozen=True)
class CitationAudit:
    """Which citation ids a report body actually uses."""

    total: int
    cited: tuple[str, ...]
    uncited: tuple[str, ...]
    marker_count: int

    @property
    def complete(self) -> bool:
        return not self.uncited

    @property
    def coverage(self) -> float:
        if self.total == 0:
            return 1.0
        return len(self.cited) / self.total

    @property
    def missing_list(self) -> str:
        return ", ".join(f"[{citation_id}]" for citation_id in self.uncited)


def audit_citations(report: str, citation_ids: list[str]) -> CitationAudit:
    """Count which of ``citation_ids`` appear as markers in ``report``."""

    known = list(dict.fromkeys(citation_ids))
    found: list[str] = []

    for match in _CITATION_MARKER.finditer(report or ""):
        citation_id = f"c{match.group(1)}"
        if citation_id in known and citation_id not in found:
            found.append(citation_id)

    cited = tuple(citation_id for citation_id in known if citation_id in found)
    uncited = tuple(citation_id for citation_id in known if citation_id not in found)

    return CitationAudit(
        total=len(known),
        cited=cited,
        uncited=uncited,
        marker_count=len(_CITATION_MARKER.findall(report or "")),
    )


def unmarked_claim_sentences(report: str) -> list[str]:
    """Sentences that state something without citing anything.

    A cheap heuristic used for reporting and for the repair prompt: skip
    headings, list markers, fenced code and table rows, then keep sentences long
    enough to carry a claim that has no marker.
    """

    in_fence = False
    claims: list[str] = []
    blocked = False

    for raw_line in (report or "").splitlines():
        if raw_line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _STRUCTURAL.match(raw_line):
            continue
        blocked = False
        for sentence in _SENTENCE_BREAK.split(raw_line):
            text = sentence.strip()
            if not text or _CITATION_MARKER.search(text):
                continue
            if len(text.split()) < 6:
                continue
            claims.append(text)

    return claims


def citation_ids_for(evidence_count: int) -> list[str]:
    """Citation ids in the order ``map_evidence_to_citations`` assigns them."""

    return [f"c{index}" for index in range(1, evidence_count + 1)]


_CJK_CHAR = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def detect_report_language(question: str) -> str:
    """Name the language a report should be written in.

    "Answer in the same language as the question" is not reliable enough: with
    English evidence and a Chinese evidence marker in the prompt, the model
    sometimes drifts. Naming the language explicitly removes the ambiguity.
    """

    sample = (question or "").strip()
    if not sample:
        return "English"
    cjk = len(_CJK_CHAR.findall(sample))
    # A mostly-English question that names a Chinese concept should still be
    # answered in English, so the threshold is deliberately high.
    return "Chinese" if cjk / len(sample) >= 0.2 else "English"
