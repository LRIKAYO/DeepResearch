"""Metric math for retrieval evaluation.

Everything in this module is pure arithmetic over logical passage keys
``(document_key, chunk_index)``. It never touches a database, the network, or an
embedding provider, so the same functions serve live API runs and ``--replay``
runs over frozen rankings.

Definitions used throughout the report:

* ``Recall@k`` - relevant passages found in the top ``k`` divided by all
  relevant passages for the case. Unanswerable cases have no recall and are
  excluded from recall averages.
* ``MRR`` - reciprocal rank of the first relevant passage (0 when none is
  retrieved), averaged over answerable cases.
* ``nDCG@k`` - binary-relevance nDCG with the ideal ranking truncated at
  ``min(len(relevant), k)``.
* ``hard-negative hit rate`` - fraction of hard-negative cases in which at
  least one declared distractor appears in the top ``k``. Lower is better; it
  is a failure rate, not a quality score.
* ``abstain`` - the retrieval policy abstains when no returned passage scores
  at least the configured threshold (or when nothing is returned). A case is
  abstain-correct when unanswerable cases abstain and answerable cases do not.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log2
from typing import Sequence

PassageKey = tuple[str, int]


def _check_k(k: int) -> None:
    if type(k) is not int or k < 1:
        raise ValueError("k must be a positive integer")


def recall_at_k(relevant: set[PassageKey], ranked: Sequence[PassageKey], k: int = 5) -> float:
    if not relevant:
        raise ValueError("Recall requires non-empty ground truth")
    _check_k(k)
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def macro_recall(values: Sequence[float]) -> float:
    """Unweighted mean of per-case recall values."""
    if not values:
        raise ValueError("Macro recall requires non-empty values")
    if any(not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("Macro recall values must be in [0, 1]")
    return sum(values) / len(values)


def reciprocal_rank(relevant: set[PassageKey], ranked: Sequence[PassageKey], k: int = 5) -> float:
    if not relevant:
        raise ValueError("MRR requires non-empty ground truth")
    _check_k(k)
    for position, key in enumerate(ranked[:k], start=1):
        if key in relevant:
            return 1.0 / position
    return 0.0


def ndcg_at_k(relevant: set[PassageKey], ranked: Sequence[PassageKey], k: int = 5) -> float:
    if not relevant:
        raise ValueError("nDCG requires non-empty ground truth")
    _check_k(k)
    dcg = sum(
        1.0 / log2(position + 1)
        for position, key in enumerate(ranked[:k], start=1)
        if key in relevant
    )
    ideal = sum(1.0 / log2(position + 1) for position in range(1, min(len(relevant), k) + 1))
    return dcg / ideal


def hard_negative_hit(
    distractors: set[PassageKey], ranked: Sequence[PassageKey], k: int = 5
) -> bool:
    _check_k(k)
    return any(key in distractors for key in ranked[:k])


def should_abstain(scores: Sequence[float | None], threshold: float) -> bool:
    """Return whether none of the returned evidence reaches the threshold.

    The threshold is a **cosine similarity**, so it must be compared against the
    best cosine among the returned passages, not against whatever happens to be
    rank 1. Under cosine-only ranking those were the same value; once ranking is
    fused with a lexical signal they are not, and comparing the threshold to the
    rank-1 score silently refuses answerable questions that had a close-enough
    passage one position down.

    ``scores`` is in rank order. An empty ranking always abstains. If every score
    is missing the run cannot judge itself and does not abstain.
    """

    if not 0.0 <= threshold <= 1.0:
        raise ValueError("abstain threshold must be between 0 and 1")
    if not scores:
        return True

    available = [score for score in scores if score is not None]
    if not available:
        return False

    return max(available) < threshold


def percentile(values: Sequence[float], percent: float) -> float | None:
    """Nearest-rank percentile (no interpolation)."""
    if not values:
        return None
    if not 0.0 <= percent <= 100.0:
        raise ValueError("percent must be between 0 and 100")
    ordered = sorted(values)
    rank = max(1, ceil(percent / 100.0 * len(ordered)))
    return ordered[rank - 1]


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


@dataclass(frozen=True)
class CaseResult:
    """Per-case evaluation outcome for one ranking."""

    case_id: str
    project_key: str
    difficulty: str
    relevant: tuple[PassageKey, ...]
    distractors: tuple[PassageKey, ...]
    ranked: tuple[PassageKey, ...]
    scores: tuple[float | None, ...]
    latency_ms: float | None
    abstained: bool
    cross_lingual: bool
    multi_hop: bool
    k: int

    @property
    def is_unanswerable(self) -> bool:
        return not self.relevant

    @property
    def relevant_count(self) -> int:
        return len(self.relevant)

    @property
    def hit_count(self) -> int:
        return len(set(self.relevant).intersection(self.ranked[: self.k]))

    @property
    def recall(self) -> float | None:
        if self.is_unanswerable:
            return None
        return self.hit_count / self.relevant_count

    @property
    def reciprocal_rank(self) -> float | None:
        if self.is_unanswerable:
            return None
        return reciprocal_rank(set(self.relevant), self.ranked, self.k)

    @property
    def ndcg(self) -> float | None:
        if self.is_unanswerable:
            return None
        return ndcg_at_k(set(self.relevant), self.ranked, self.k)

    @property
    def hard_negative_hit(self) -> bool | None:
        if not self.distractors:
            return None
        return hard_negative_hit(set(self.distractors), self.ranked, self.k)

    @property
    def abstain_correct(self) -> bool:
        if self.is_unanswerable:
            return self.abstained
        return not self.abstained

    @property
    def top1(self) -> PassageKey | None:
        return self.ranked[0] if self.ranked else None

    @property
    def top1_score(self) -> float | None:
        return self.scores[0] if self.scores else None


@dataclass(frozen=True)
class AggregateMetrics:
    k: int
    case_count: int
    answerable_count: int
    unanswerable_count: int
    macro_recall: float | None
    micro_recall: float | None
    mrr: float | None
    ndcg: float | None
    hard_negative_case_count: int
    hard_negative_hit_rate: float | None
    cross_lingual_case_count: int
    cross_lingual_recall: float | None
    unanswerable_abstain_rate: float | None
    false_abstain_rate: float | None
    abstain_correctness: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None

    def as_dict(self) -> dict:
        return {
            "k": self.k,
            "case_count": self.case_count,
            "answerable_count": self.answerable_count,
            "unanswerable_count": self.unanswerable_count,
            "macro_recall": self.macro_recall,
            "micro_recall": self.micro_recall,
            "mrr": self.mrr,
            "ndcg": self.ndcg,
            "hard_negative_case_count": self.hard_negative_case_count,
            "hard_negative_hit_rate": self.hard_negative_hit_rate,
            "cross_lingual_case_count": self.cross_lingual_case_count,
            "cross_lingual_recall": self.cross_lingual_recall,
            "unanswerable_abstain_rate": self.unanswerable_abstain_rate,
            "false_abstain_rate": self.false_abstain_rate,
            "abstain_correctness": self.abstain_correctness,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
        }


def aggregate_metrics(results: Sequence[CaseResult]) -> AggregateMetrics:
    if not results:
        raise ValueError("aggregate_metrics requires at least one case")
    k_values = {result.k for result in results}
    if len(k_values) != 1:
        raise ValueError("All case results must use the same k")
    k = results[0].k

    answerable = [result for result in results if not result.is_unanswerable]
    unanswerable = [result for result in results if result.is_unanswerable]
    hard_negative_cases = [result for result in results if result.distractors]
    cross_lingual = [result for result in answerable if result.cross_lingual]

    recall_values = [result.recall for result in answerable if result.recall is not None]
    total_hits = sum(result.hit_count for result in answerable)
    total_relevant = sum(result.relevant_count for result in answerable)
    latencies = [result.latency_ms for result in results if result.latency_ms is not None]

    return AggregateMetrics(
        k=k,
        case_count=len(results),
        answerable_count=len(answerable),
        unanswerable_count=len(unanswerable),
        macro_recall=_mean(recall_values),
        micro_recall=(total_hits / total_relevant) if total_relevant else None,
        mrr=_mean(
            [result.reciprocal_rank for result in answerable if result.reciprocal_rank is not None]
        ),
        ndcg=_mean([result.ndcg for result in answerable if result.ndcg is not None]),
        hard_negative_case_count=len(hard_negative_cases),
        hard_negative_hit_rate=_mean(
            [1.0 if result.hard_negative_hit else 0.0 for result in hard_negative_cases]
        ),
        cross_lingual_case_count=len(cross_lingual),
        cross_lingual_recall=_mean(
            [result.recall for result in cross_lingual if result.recall is not None]
        ),
        unanswerable_abstain_rate=_mean(
            [1.0 if result.abstained else 0.0 for result in unanswerable]
        ),
        false_abstain_rate=_mean([1.0 if result.abstained else 0.0 for result in answerable]),
        abstain_correctness=_mean([1.0 if result.abstain_correct else 0.0 for result in results]),
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
    )
