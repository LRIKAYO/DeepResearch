"""Citation verification: does a cited passage actually support its claim?

The Writer produces a report with ``[cN]`` markers. The Verifier checks each
marker against the passage it points at and records one of three verdicts. This
is what separates "retrieval produced sources" from "the report can be trusted":
a citation that is merely listed is not evidence of anything.

Verification is advisory. A verifier failure must never discard a report that
already exists, so every error path degrades to "no verdict" instead of raising.
"""

import logging
import re
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

logger = logging.getLogger(__name__)

MAX_PASSAGE_CHARS = 1200
MAX_CLAIM_CHARS = 600

Support = Literal["full", "partial", "none"]

_CITATION_MARKER = re.compile(r"\[c([1-9][0-9]*)\]")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?。！？;；])")


class VerificationResult(BaseModel):
    """One verdict for one citation id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: StrictStr = Field(pattern=r"^c[1-9][0-9]*$")
    support: Support
    reason: StrictStr = Field(min_length=1, max_length=300)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        reason = " ".join(value.split())
        if not reason:
            raise ValueError("verification reason cannot be empty")
        return reason


class VerificationBatch(BaseModel):
    """Structured verifier output."""

    model_config = ConfigDict(extra="forbid")

    results: list[VerificationResult] = Field(default_factory=list)


VerificationPayload: TypeAlias = dict[str, Any]


def extract_claims(report: str) -> dict[str, list[str]]:
    """Map each citation id to the report sentences that cite it."""

    claims: dict[str, list[str]] = {}

    for raw_sentence in _SENTENCE_BREAK.split(report):
        sentence = " ".join(raw_sentence.split())
        if not sentence:
            continue
        for match in _CITATION_MARKER.finditer(sentence):
            citation_id = f"c{match.group(1)}"
            bucket = claims.setdefault(citation_id, [])
            if sentence not in bucket:
                bucket.append(sentence)

    return claims


def build_verification_items(state: dict) -> list[dict[str, str]]:
    """Pair every citation with the claim it supports and the full passage."""

    citations = state.get("citations") or []
    evidence = state.get("evidence") or []
    claims = extract_claims(state.get("report") or "")

    items: list[dict[str, str]] = []
    for index, citation in enumerate(citations):
        if not isinstance(citation, dict):
            continue
        citation_id = citation.get("citation_id")
        if not isinstance(citation_id, str):
            continue

        passage = ""
        if index < len(evidence) and isinstance(evidence[index], dict):
            passage = str(evidence[index].get("content") or "")
        if not passage:
            passage = str(citation.get("excerpt") or "")

        claim_sentences = claims.get(citation_id, [])
        claim = " ".join(claim_sentences) if claim_sentences else ""

        items.append(
            {
                "citation_id": citation_id,
                "claim": claim[:MAX_CLAIM_CHARS],
                "passage": passage[:MAX_PASSAGE_CHARS],
                "source": str(citation.get("source_label") or ""),
            }
        )

    return items


def coerce_verdicts(raw: object, valid_ids: set[str]) -> list[VerificationPayload]:
    """Normalize verifier output, dropping anything it was not asked about."""

    if isinstance(raw, VerificationBatch):
        results = raw.results
    elif isinstance(raw, dict):
        try:
            results = VerificationBatch.model_validate(raw).results
        except ValidationError:
            logger.warning("verifier returned an invalid batch; keeping no verdicts")
            return []
    elif isinstance(raw, list):
        try:
            results = [VerificationResult.model_validate(item) for item in raw]
        except ValidationError:
            logger.warning("verifier returned an invalid result list; keeping no verdicts")
            return []
    else:
        logger.warning("verifier returned %s; keeping no verdicts", type(raw).__name__)
        return []

    verdicts: list[VerificationPayload] = []
    seen: set[str] = set()

    for result in results:
        if result.citation_id not in valid_ids or result.citation_id in seen:
            continue
        seen.add(result.citation_id)
        verdicts.append(result.model_dump(mode="json"))

    return verdicts


def verify_citations(state: dict, verifier_impl: Any) -> dict:
    """Verifier node: annotate citations with support verdicts."""

    items = build_verification_items(state)
    if not items:
        return {"verification": []}

    # Citations the Writer listed but never used inline cannot be checked
    # against a claim; record that explicitly instead of silently passing them.
    uncited = [
        {
            "citation_id": item["citation_id"],
            "support": "none",
            "reason": "citation is listed but no report sentence cites it",
        }
        for item in items
        if not item["claim"]
    ]
    cited = [item for item in items if item["claim"]]

    verdicts: list[VerificationPayload] = list(uncited)

    if cited:
        try:
            raw = verifier_impl.invoke({"items": cited})
        except Exception:
            logger.warning("citation verification failed; keeping no verdicts", exc_info=True)
            return {"verification": verdicts}

        verdicts.extend(
            coerce_verdicts(raw, {item["citation_id"] for item in cited})
        )

    order = {item["citation_id"]: index for index, item in enumerate(items)}
    verdicts.sort(key=lambda verdict: order.get(verdict["citation_id"], 0))

    return {"verification": verdicts}
