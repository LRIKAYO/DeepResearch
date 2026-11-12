"""Unit tests for hybrid (cosine + BM25 + RRF) Project knowledge retrieval.

These tests are database-free: the ranking math and the row-to-hit assembly are
exercised with a fake session whose rows are already in cosine order, exactly as
the SQL ``ORDER BY`` would return them.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from researchflow.knowledge.retrieval import (
    RRF_K,
    bm25_scores,
    reciprocal_rank_fusion,
    search_knowledge,
    tokenize,
)


@dataclass
class _Row:
    document_id: UUID
    chunk_id: UUID
    filename: str
    content: str
    distance: float


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Returns fixed rows; the real statement is never executed."""

    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Result(self.rows)


def _row(content: str, distance: float, *, chunk_id: UUID | None = None) -> _Row:
    return _Row(
        document_id=uuid4(),
        chunk_id=chunk_id or uuid4(),
        filename="doc.md",
        content=content,
        distance=distance,
    )


def test_tokenize_keeps_whole_identifier_and_splits_camel_and_snake_case():
    tokens = tokenize("baseNameMatch max_age strict-deepEqual")

    # Whole identifiers survive, so an exact-term query can match them.
    assert "basenamematch" in tokens
    assert "max_age" in tokens
    # Camel case and snake case both contribute their word parts.
    assert tokens.count("base") == 1
    assert tokens.count("name") == 1
    assert tokens.count("match") == 1
    assert "max" in tokens
    assert "age" in tokens
    assert "strict" in tokens
    assert "deep" in tokens
    assert "equal" in tokens


def test_bm25_ranks_a_rare_exact_identifier_above_boilerplate():
    documents = [
        "The default option applies to every call.",
        "Set baseNameMatch to true to compare names exactly.",
        "The default option can be overridden per call.",
    ]

    scores = bm25_scores("baseNameMatch", documents)

    assert scores[0] == 0.0
    assert scores[2] == 0.0
    assert scores[1] > 0.0


def test_bm25_returns_zero_when_no_token_overlaps():
    documents = ["english only text", "more english text"]

    assert bm25_scores("中文查询", documents) == [0.0, 0.0]


def test_bm25_rewards_a_second_occurrence_but_saturates():
    one = bm25_scores("needle", ["needle once", "filler"])[0]
    two = bm25_scores("needle", ["needle needle", "filler"])[0]
    three = bm25_scores("needle", ["needle needle needle", "filler"])[0]

    assert 0.0 < one < two
    # Diminishing returns: the third occurrence adds less than the second.
    assert (three - two) < (two - one)


def test_rrf_fuses_rankings_and_prefers_a_candidate_seen_by_both():
    fused = reciprocal_rank_fusion(cosine_ranking=[0, 1, 2], lexical_ranking=[1])

    # Candidate 1 is cosine rank 2 but lexical rank 1, so it wins.
    assert fused[0] == 1
    assert fused == [1, 0, 2]


def test_rrf_ties_fall_back_to_cosine_order():
    assert reciprocal_rank_fusion([0, 1], []) == [0, 1]
    assert reciprocal_rank_fusion([], [0, 1]) == [0, 1]


def test_search_returns_fused_order_but_keeps_cosine_similarity_as_score():
    rows = [
        _row("generic filler", 0.10),
        _row("Set baseNameMatch to true.", 0.20),
        _row("baseNameMatch baseNameMatch details", 0.25),
    ]
    session = _FakeSession(rows)

    hits = search_knowledge(
        session,
        owner_user_id=uuid4(),
        project_id=uuid4(),
        query_text="baseNameMatch",
        query_vector=[1.0, *([0.0] * 1023)],
        limit=5,
    )

    # The lexical match is promoted, but each hit still reports its own cosine.
    assert [hit.content for hit in hits] == [
        "baseNameMatch baseNameMatch details",
        "Set baseNameMatch to true.",
        "generic filler",
    ]
    assert [hit.score for hit in hits] == pytest.approx([0.75, 0.80, 0.90])


def test_search_applies_limit_after_fusion_and_preserves_cosine_tie_break():
    earlier = UUID(int=1)
    later = UUID(int=2)
    rows = [
        _row("generic filler", 0.20, chunk_id=earlier),
        _row("generic filler", 0.20, chunk_id=later),
    ]

    hits = search_knowledge(
        _FakeSession(rows),
        owner_user_id=uuid4(),
        project_id=uuid4(),
        query_text="nothing overlaps",
        query_vector=[1.0, *([0.0] * 1023)],
        limit=1,
    )

    assert [hit.chunk_id for hit in hits] == [earlier]


def test_search_without_lexical_match_is_pure_cosine_order():
    rows = [_row("alpha", 0.1), _row("beta", 0.2), _row("gamma", 0.3)]

    hits = search_knowledge(
        _FakeSession(rows),
        owner_user_id=uuid4(),
        project_id=uuid4(),
        query_text="zzz-no-such-token",
        query_vector=[1.0, *([0.0] * 1023)],
        limit=10,
    )

    assert [hit.content for hit in hits] == ["alpha", "beta", "gamma"]
    assert [hit.score for hit in hits] == pytest.approx([0.9, 0.8, 0.7])


def test_search_skips_bm25_for_cjk_queries_and_keeps_cosine_order():
    rows = [
        _row("generic filler", 0.10),
        _row("cssesc options are global", 0.20),
        _row("cssesc options again", 0.30),
    ]

    hits = search_knowledge(
        _FakeSession(rows),
        owner_user_id=uuid4(),
        project_id=uuid4(),
        # The Latin identifiers alone would give rows 1 and 2 a lexical boost.
        query_text="cssesc 的全局 options 默认值？",
        query_vector=[1.0, *([0.0] * 1023)],
        limit=5,
    )

    assert [hit.content for hit in hits] == [
        "generic filler",
        "cssesc options are global",
        "cssesc options again",
    ]


def test_search_empty_project_returns_empty_list():
    assert (
        search_knowledge(
            _FakeSession([]),
            owner_user_id=uuid4(),
            project_id=uuid4(),
            query_text="anything",
            query_vector=[1.0, *([0.0] * 1023)],
            limit=5,
        )
        == []
    )


def test_rrf_constant_is_the_documented_sixty():
    assert RRF_K == 60

def test_search_can_disable_the_lexical_signal():
    rows = [
        _row("generic filler", 0.10),
        _row("Set baseNameMatch to true.", 0.20),
        _row("baseNameMatch baseNameMatch details", 0.25),
    ]
    session = _FakeSession(rows)

    hits = search_knowledge(
        session,
        owner_user_id=uuid4(),
        project_id=uuid4(),
        query_text="baseNameMatch",
        query_vector=[1.0, *([0.0] * 1023)],
        limit=5,
        use_lexical=False,
    )

    # Pure cosine order; the lexical promotion is gone.
    assert [hit.content for hit in hits] == [
        "generic filler",
        "Set baseNameMatch to true.",
        "baseNameMatch baseNameMatch details",
    ]
