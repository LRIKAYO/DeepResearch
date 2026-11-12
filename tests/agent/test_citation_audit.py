"""Citation coverage audit and the Writer repair pass."""

import pytest

from researchflow.agent.citation_audit import (
    audit_citations,
    citation_ids_for,
    unmarked_claim_sentences,
)
from researchflow.agent.runtime import _WriterWithCitationAudit


class FakeRunnable:
    def __init__(self, result):
        self.result = result
        self.payloads = []

    def invoke(self, payload):
        self.payloads.append(payload)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def evidence(count: int) -> list[dict]:
    return [
        {
            "source_type": "temporary_research",
            "source_label": f"https://example.com/{index}",
            "content": f"passage {index}",
            "provenance": {"url": f"https://example.com/{index}"},
        }
        for index in range(1, count + 1)
    ]


# --- audit -------------------------------------------------------------------


def test_audit_marks_a_fully_cited_report_complete():
    audit = audit_citations("Precision defaults to 3 [c1]. The option is digits [c2].", ["c1", "c2"])

    assert audit.complete
    assert audit.uncited == ()
    assert audit.coverage == pytest.approx(1.0)


def test_audit_reports_listed_but_uncited_ids():
    audit = audit_citations("Only this sentence is cited [c1].", ["c1", "c2", "c3"])

    assert not audit.complete
    assert audit.cited == ("c1",)
    assert audit.uncited == ("c2", "c3")
    assert audit.missing_list == "[c2], [c3]"


def test_audit_counts_a_marker_once_and_ignores_repeats():
    audit = audit_citations("a [c1] b [c1] c [c1][c2]", ["c1", "c2"])

    assert audit.marker_count == 4
    assert audit.cited == ("c1", "c2")


def test_audit_ignores_ids_that_are_not_in_the_evidence_list():
    audit = audit_citations("cited [c9] only", ["c1"])

    assert audit.cited == ()
    assert audit.uncited == ("c1",)


def test_audit_handles_an_empty_inventory():
    audit = audit_citations("no sources at all", [])

    assert audit.complete
    assert audit.coverage == pytest.approx(1.0)


def test_citation_ids_follow_evidence_order():
    assert citation_ids_for(3) == ["c1", "c2", "c3"]


# --- unmarked sentences ------------------------------------------------------


def test_unmarked_claims_skip_marked_and_short_lines():
    report = (
        "# Heading without a marker\n"
        "- bullet [c1]\n"
        "The system returns a documented default value of 3.\n"
        "ok [c2]\n"
    )

    claims = unmarked_claim_sentences(report)

    assert claims == ["The system returns a documented default value of 3."]


def test_unmarked_claims_ignore_fenced_code():
    report = "```js\nconst value = computeTheDefault();\n```\n"

    assert unmarked_claim_sentences(report) == []


# --- writer repair -----------------------------------------------------------


def _writer(draft_result, repair_result):
    draft = FakeRunnable(draft_result)
    repair = FakeRunnable(repair_result)
    return _WriterWithCitationAudit(draft, repair), draft, repair


def test_writer_skips_the_repair_when_every_id_is_cited():
    writer, draft, repair = _writer("cited [c1] and [c2]", "should not run")

    assert writer.invoke({"evidence": evidence(2)}) == "cited [c1] and [c2]"
    assert len(draft.payloads) == 1
    assert repair.payloads == []


def test_writer_repairs_missing_ids_once():
    writer, _draft, repair = _writer(
        "only one marker here [c1]",
        "now every marker is present [c1] [c2] [c3]",
    )

    result = writer.invoke({"evidence": evidence(3)})

    assert result == "now every marker is present [c1] [c2] [c3]"
    assert len(repair.payloads) == 1
    assert repairable(repair)


def repairable(repair: FakeRunnable) -> bool:
    payload = repair.payloads[0]
    return payload.get("missing") == "[c2], [c3]" and "only one marker" in payload["report"]


def test_writer_keeps_the_draft_when_the_repair_throws():
    writer, _draft, _repair = _writer("only [c1]", RuntimeError("provider down"))

    assert writer.invoke({"evidence": evidence(2)}) == "only [c1]"


def test_writer_keeps_the_draft_when_the_repair_does_not_improve():
    writer, _draft, _repair = _writer("only [c1]", "still only [c1]")

    assert writer.invoke({"evidence": evidence(3)}) == "only [c1]"


def test_writer_keeps_the_draft_when_the_repair_returns_blank():
    writer, _draft, _repair = _writer("only [c1]", "   ")

    assert writer.invoke({"evidence": evidence(2)}) == "only [c1]"


def test_writer_does_not_repair_when_there_is_no_evidence():
    writer, _draft, repair = _writer("no sources needed", "nope")

    assert writer.invoke({"evidence": []}) == "no sources needed"
    assert repair.payloads == []

# --- report language ---------------------------------------------------------


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What does arc.digits() return?", "English"),
        ("d3.zip 在参数长度不一致时返回什么？", "Chinese"),
        ("Explain 数组 zip", "English"),
        ("arc.digits() 默认返回什么", "Chinese"),
        ("", "English"),
    ],
)
def test_detect_report_language(question, expected):
    from researchflow.agent.citation_audit import detect_report_language

    assert detect_report_language(question) == expected


def test_writer_inputs_name_the_report_language():
    from researchflow.agent.runtime import _writer_inputs

    inputs = _writer_inputs(
        {"research_query": "d3.zip 的行为是什么？", "sub_questions": [], "evidence": []}
    )

    assert inputs["report_language"] == "Chinese"


def test_writer_inputs_default_to_english_for_an_empty_query():
    from researchflow.agent.runtime import _writer_inputs

    assert _writer_inputs({"evidence": []})["report_language"] == "English"
