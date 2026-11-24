import pytest
from pydantic import ValidationError

from researchflow.agent.verification import (
    MAX_CLAIM_CHARS,
    MAX_PASSAGE_CHARS,
    VerificationBatch,
    VerificationResult,
    build_verification_items,
    coerce_verdicts,
    extract_claims,
    verify_citations,
)


def citation(citation_id: str = "c1", source_label: str = "ops.md", excerpt: str = "ex"):
    return {
        "citation_id": citation_id,
        "source_type": "user_upload",
        "source_label": source_label,
        "excerpt": excerpt,
        "provenance": {
            "document_id": "11111111-1111-1111-1111-111111111111",
            "chunk_id": "22222222-2222-2222-2222-222222222222",
            "filename": "ops.md",
        },
    }


def evidence(content: str = "校准每周一进行"):
    return {
        "source_type": "user_upload",
        "source_label": "ops.md",
        "content": content,
        "retrieval_score": 0.9,
        "provenance": {
            "document_id": "11111111-1111-1111-1111-111111111111",
            "chunk_id": "22222222-2222-2222-2222-222222222222",
            "filename": "ops.md",
        },
    }


class FakeVerifier:
    def __init__(self, result):
        self.result = result
        self.received_payloads = []

    def invoke(self, payload):
        self.received_payloads.append(payload)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


# --- VerificationResult -----------------------------------------------------


def test_result_requires_a_citation_id_pattern():
    with pytest.raises(ValidationError):
        VerificationResult(citation_id="1", support="full", reason="ok")


def test_result_rejects_an_unknown_support_level():
    with pytest.raises(ValidationError):
        VerificationResult(citation_id="c1", support="maybe", reason="ok")


def test_result_normalizes_the_reason():
    result = VerificationResult(citation_id="c2", support="partial", reason="  a   b  ")

    assert result.reason == "a b"


def test_result_rejects_a_blank_reason():
    with pytest.raises(ValidationError):
        VerificationResult(citation_id="c1", support="full", reason="   ")


# --- extract_claims ---------------------------------------------------------


def test_extract_claims_maps_each_marker_to_its_sentence():
    report = "校准每周一进行 [c1]。维护每月一次 [c2]。两者不冲突 [c1][c2]。"

    claims = extract_claims(report)

    assert claims["c1"] == ["校准每周一进行 [c1]。", "两者不冲突 [c1][c2]。"]
    assert claims["c2"] == ["维护每月一次 [c2]。", "两者不冲突 [c1][c2]。"]


def test_extract_claims_ignores_text_without_markers():
    assert extract_claims("没有引用的报告。") == {}


def test_extract_claims_skips_fenced_code_blocks():
    report = (
        "结论见如下代码示例：\n"
        "```python\n"
        "item = results[c1]  # not a citation [c2].\n"
        "```\n"
        "实际校准每周一进行 [c1]。"
    )

    claims = extract_claims(report)

    assert claims == {"c1": ["实际校准每周一进行 [c1]。"]}
    assert "c2" not in claims


def test_verify_citations_treats_code_fence_only_marker_as_uncited():
    verifier = FakeVerifier(
        {"results": [{"citation_id": "c1", "support": "full", "reason": "一致"}]}
    )
    report = (
        "校准每周一进行 [c1]。\n"
        "```js\n"
        "const sample = arr[c2];\n"
        "```\n"
    )

    update = verify_citations(
        {
            "citations": [citation("c1"), citation("c2")],
            "evidence": [evidence("a"), evidence("b")],
            "report": report,
        },
        verifier,
    )

    assert [item["citation_id"] for item in verifier.received_payloads[0]["items"]] == [
        "c1"
    ]
    assert update["verification"] == [
        {"citation_id": "c1", "support": "full", "reason": "一致"},
        {
            "citation_id": "c2",
            "support": "none",
            "reason": "citation is listed but no report sentence cites it",
        },
    ]


# --- build_verification_items ----------------------------------------------


def test_build_items_pairs_citation_with_evidence_content():
    items = build_verification_items(
        {
            "citations": [citation()],
            "evidence": [evidence()],
            "report": "校准每周一进行 [c1]。",
        }
    )

    assert items == [
        {
            "citation_id": "c1",
            "claim": "校准每周一进行 [c1]。",
            "passage": "校准每周一进行",
            "source": "ops.md",
        }
    ]


def test_build_items_falls_back_to_the_excerpt():
    items = build_verification_items(
        {"citations": [citation(excerpt="仅有摘录")], "evidence": [], "report": "x [c1]."}
    )

    assert items[0]["passage"] == "仅有摘录"


def test_build_items_leaves_the_claim_empty_when_uncited():
    items = build_verification_items(
        {
            "citations": [citation()],
            "evidence": [evidence()],
            "report": "报告没有引用任何东西。",
        }
    )

    assert items[0]["claim"] == ""


def test_build_items_truncates_long_inputs():
    items = build_verification_items(
        {
            "citations": [citation()],
            "evidence": [evidence(content="x" * 5000)],
            "report": "y" * 5000 + " [c1].",
        }
    )

    assert len(items[0]["passage"]) == MAX_PASSAGE_CHARS
    assert len(items[0]["claim"]) == MAX_CLAIM_CHARS


# --- coerce_verdicts --------------------------------------------------------


def test_coerce_accepts_a_batch_model():
    raw = VerificationBatch(
        results=[VerificationResult(citation_id="c1", support="full", reason="ok")]
    )

    assert coerce_verdicts(raw, {"c1"}) == [
        {"citation_id": "c1", "support": "full", "reason": "ok"}
    ]


def test_coerce_accepts_a_dict():
    raw = {"results": [{"citation_id": "c1", "support": "none", "reason": "no"}]}

    assert coerce_verdicts(raw, {"c1"})[0]["support"] == "none"


def test_coerce_drops_ids_it_was_not_asked_about():
    raw = {
        "results": [
            {"citation_id": "c9", "support": "full", "reason": "invented"},
            {"citation_id": "c1", "support": "full", "reason": "real"},
        ]
    }

    assert [item["citation_id"] for item in coerce_verdicts(raw, {"c1"})] == ["c1"]


def test_coerce_drops_duplicate_verdicts():
    raw = {
        "results": [
            {"citation_id": "c1", "support": "full", "reason": "first"},
            {"citation_id": "c1", "support": "none", "reason": "second"},
        ]
    }

    verdicts = coerce_verdicts(raw, {"c1"})

    assert len(verdicts) == 1
    assert verdicts[0]["reason"] == "first"


@pytest.mark.parametrize(
    "raw",
    [
        {"results": [{"citation_id": "c1", "support": "invalid", "reason": "x"}]},
        [{"citation_id": "bad-id", "support": "full", "reason": "x"}],
        42,
        None,
    ],
)
def test_coerce_returns_no_verdicts_for_invalid_output(raw):
    assert coerce_verdicts(raw, {"c1"}) == []


# --- verify_citations -------------------------------------------------------


def test_verify_citations_returns_nothing_without_citations():
    assert verify_citations({"citations": []}, FakeVerifier({})) == {"verification": []}


def test_verify_citations_calls_the_verifier_once_for_all_cited_items():
    verifier = FakeVerifier(
        {
            "results": [
                {"citation_id": "c1", "support": "full", "reason": "匹配"},
                {"citation_id": "c2", "support": "partial", "reason": "部分"},
            ]
        }
    )

    update = verify_citations(
        {
            "citations": [citation("c1"), citation("c2")],
            "evidence": [evidence("a"), evidence("b")],
            "report": "结论一 [c1]。结论二 [c2]。",
        },
        verifier,
    )

    assert len(verifier.received_payloads) == 1
    assert [item["citation_id"] for item in verifier.received_payloads[0]["items"]] == [
        "c1",
        "c2",
    ]
    assert update["verification"] == [
        {"citation_id": "c1", "support": "full", "reason": "匹配"},
        {"citation_id": "c2", "support": "partial", "reason": "部分"},
    ]


def test_verify_citations_flags_listed_but_uncited_sources():
    verifier = FakeVerifier({"results": []})

    update = verify_citations(
        {
            "citations": [citation("c1"), citation("c2")],
            "evidence": [evidence(), evidence()],
            "report": "只引用了第一条 [c1]。",
        },
        verifier,
    )

    assert [item["citation_id"] for item in verifier.received_payloads[0]["items"]] == [
        "c1"
    ]
    assert update["verification"][-1] == {
        "citation_id": "c2",
        "support": "none",
        "reason": "citation is listed but no report sentence cites it",
    }


def test_verify_citations_never_raises_when_the_verifier_fails():
    update = verify_citations(
        {
            "citations": [citation("c1")],
            "evidence": [evidence()],
            "report": "结论 [c1]。",
        },
        FakeVerifier(RuntimeError("provider down")),
    )

    assert update == {"verification": []}


def test_verify_citations_keeps_verdicts_in_citation_order():
    verifier = FakeVerifier(
        {
            "results": [
                {"citation_id": "c2", "support": "none", "reason": "b"},
                {"citation_id": "c1", "support": "full", "reason": "a"},
            ]
        }
    )

    update = verify_citations(
        {
            "citations": [citation("c1"), citation("c2")],
            "evidence": [evidence(), evidence()],
            "report": "一 [c1]。二 [c2]。",
        },
        verifier,
    )

    assert [item["citation_id"] for item in update["verification"]] == ["c1", "c2"]
