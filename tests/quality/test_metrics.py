"""Hand-computed metric fixtures for evaluations.metrics."""

from __future__ import annotations

from math import log2

import pytest

from evaluations.metrics import (
    CaseResult,
    aggregate_metrics,
    hard_negative_hit,
    ndcg_at_k,
    percentile,
    reciprocal_rank,
    recall_at_k,
    should_abstain,
)


@pytest.mark.parametrize(("relevant", "ranked", "k", "expected"), [
    ({"a", "b"}, ["a", "b"], 5, 1.0),
    ({"a", "b"}, ["a", "x"], 5, 0.5),
    ({"a", "b"}, ["b", "a"], 5, 1.0),
    ({"a"}, ["x"], 5, 0.0),
    ({"a"}, ["x", "y", "z", "u", "v", "a"], 5, 0.0),
    ({"a", "b"}, ["a", "a", "x"], 5, 0.5),
    ({"a", "b", "c"}, ["a", "x", "b"], 2, 1 / 3),
])
def test_recall_uses_relevant_set_and_top_k(relevant, ranked, k, expected):
    assert recall_at_k(relevant, ranked, k) == pytest.approx(expected)


def test_recall_rejects_empty_ground_truth_and_bad_k():
    with pytest.raises(ValueError):
        recall_at_k(set(), ["a"])
    with pytest.raises(ValueError):
        recall_at_k({"a"}, ["a"], 0)


@pytest.mark.parametrize(("relevant", "ranked", "k", "expected"), [
    ({"a"}, ["a"], 5, 1.0),
    ({"a"}, ["x", "a"], 5, 0.5),
    ({"a", "b"}, ["x", "b", "a"], 5, 0.5),
    ({"a"}, ["x"], 5, 0.0),
    ({"a"}, ["x", "y", "a"], 2, 0.0),
])
def test_reciprocal_rank(relevant, ranked, k, expected):
    assert reciprocal_rank(relevant, ranked, k) == pytest.approx(expected)


@pytest.mark.parametrize(("relevant", "ranked", "k", "expected"), [
    ({"a"}, ["a"], 5, 1.0),
    ({"a"}, ["x", "a"], 5, 1.0 / log2(3)),
    ({"a", "b"}, ["a", "x", "b"], 5, (1.0 + 1.0 / log2(4)) / (1.0 + 1.0 / log2(3))),
    ({"a", "b", "c"}, ["a", "b"], 2, 1.0),
    ({"a"}, ["x"], 5, 0.0),
])
def test_ndcg_binary_relevance_and_ideal_truncation(relevant, ranked, k, expected):
    assert ndcg_at_k(relevant, ranked, k) == pytest.approx(expected)


def test_hard_negative_hit_respects_cutoff():
    assert hard_negative_hit({("d", 0)}, [("a", 0), ("d", 0)], 5) is True
    assert hard_negative_hit({("d", 0)}, [("d", 0), ("a", 0)], 1) is True
    assert hard_negative_hit({("d", 0)}, [("a", 0), ("d", 0)], 1) is False
    assert hard_negative_hit({("d", 0)}, [], 5) is False


@pytest.mark.parametrize(("scores", "threshold", "expected"), [
    ([], 0.6, True),
    ([0.59], 0.6, True),
    ([0.60], 0.6, False),
    ([0.90], 0.6, False),
    ([None], 0.6, False),
    ([0.90, 0.10], 0.6, False),
    # The threshold is a cosine similarity, so the best returned score decides.
    # A fused ranking can put a lexically-promoted, less similar chunk at rank 1;
    # abstaining because of that would refuse a question the system can answer.
    ([0.40, 0.75], 0.6, False),
    ([0.40, 0.50], 0.6, True),
    ([None, 0.70], 0.6, False),
    ([0.10, None, 0.20], 0.6, True),
])
def test_abstain_policy_uses_the_best_returned_score(scores, threshold, expected):
    assert should_abstain(scores, threshold) is expected


def test_percentile_is_nearest_rank():
    assert percentile([], 50) is None
    assert percentile([4, 1, 3, 2], 50) == 2
    assert percentile([4, 1, 3, 2], 95) == 4
    assert percentile([5], 50) == 5
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10


def _case(
    case_id: str,
    *,
    relevant=(),
    distractors=(),
    ranked=(),
    scores=(),
    latency=10.0,
    abstained=False,
    cross_lingual=False,
    multi_hop=False,
    k=5,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        project_key="p",
        difficulty="medium",
        relevant=tuple(relevant),
        distractors=tuple(distractors),
        ranked=tuple(ranked),
        scores=tuple(scores),
        latency_ms=latency,
        abstained=abstained,
        cross_lingual=cross_lingual,
        multi_hop=multi_hop,
        k=k,
    )


def test_case_result_properties_for_unanswerable_cases():
    case = _case("u", distractors=[("d", 0)], ranked=[("d", 0)], scores=[0.9], abstained=False)
    assert case.is_unanswerable is True
    assert case.recall is None
    assert case.reciprocal_rank is None
    assert case.ndcg is None
    assert case.hard_negative_hit is True
    assert case.abstain_correct is False


def test_aggregate_metrics_on_hand_computed_fixture():
    results = [
        _case(
            "c1",
            relevant=[("a", 0), ("a", 1)],
            distractors=[("x", 0)],
            ranked=[("a", 0), ("x", 0)],
            scores=[0.9, 0.8],
            latency=10.0,
        ),
        _case(
            "c2",
            relevant=[("b", 0)],
            distractors=[("b", 1)],
            ranked=[("x", 0), ("b", 0), ("b", 1)],
            scores=[0.9, 0.8, 0.7],
            latency=20.0,
            cross_lingual=True,
            k=3,
        ),
        _case(
            "c3",
            distractors=[("d", 0)],
            ranked=[("d", 0)],
            scores=[0.9],
            latency=30.0,
        ),
        _case(
            "c4",
            distractors=[("e", 0)],
            ranked=[],
            scores=[],
            latency=40.0,
            abstained=True,
        ),
    ]
    # c1 uses k=5 while c2 uses k=3, so aggregate would reject; use k=3 for all.
    results = [
        CaseResult(**{**result.__dict__, "k": 3}) for result in results
    ]
    metrics = aggregate_metrics(results)

    assert metrics.case_count == 4
    assert metrics.answerable_count == 2
    assert metrics.unanswerable_count == 2
    assert metrics.macro_recall == pytest.approx(0.75)
    assert metrics.micro_recall == pytest.approx(2 / 3)
    assert metrics.mrr == pytest.approx(0.75)
    assert metrics.ndcg == pytest.approx((1.0 / (1.0 + 1.0 / log2(3)) + 1.0 / log2(3)) / 2)
    assert metrics.hard_negative_case_count == 4
    assert metrics.hard_negative_hit_rate == pytest.approx(0.75)
    assert metrics.cross_lingual_case_count == 1
    assert metrics.cross_lingual_recall == pytest.approx(1.0)
    assert metrics.unanswerable_abstain_rate == pytest.approx(0.5)
    assert metrics.false_abstain_rate == pytest.approx(0.0)
    assert metrics.abstain_correctness == pytest.approx(0.75)
    assert metrics.latency_p50_ms == pytest.approx(20.0)
    assert metrics.latency_p95_ms == pytest.approx(40.0)


def test_aggregate_rejects_mixed_k_and_empty_results():
    with pytest.raises(ValueError):
        aggregate_metrics([])
    with pytest.raises(ValueError):
        aggregate_metrics([_case("a", relevant=[("a", 0)], k=5), _case("b", relevant=[("b", 0)], k=3)])
