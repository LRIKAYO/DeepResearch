import pytest
from pydantic import ValidationError

from researchflow.agent.plan import PassthroughPlanner
from researchflow.agent.plan import (
    MAX_SUB_QUESTIONS,
    ResearchPlan,
    coerce_sub_questions,
    normalize_research_query,
    plan_research,
)


class FakePlanner:
    def __init__(self, result):
        self.result = result
        self.received_payloads = []

    def invoke(self, payload):
        self.received_payloads.append(payload)
        return self.result


# --- ResearchPlan -----------------------------------------------------------


def test_plan_strips_and_dedupes_sub_questions():
    plan = ResearchPlan(
        sub_questions=[
            "  校准周期是什么  ",
            "校准周期是什么",
            "维护与校准是否冲突",
        ]
    )

    assert plan.sub_questions == ["校准周期是什么", "维护与校准是否冲突"]


def test_plan_drops_empty_questions():
    plan = ResearchPlan(sub_questions=["   ", "有效问题"])

    assert plan.sub_questions == ["有效问题"]


def test_plan_caps_the_number_of_sub_questions():
    plan = ResearchPlan(sub_questions=[f"q{index}" for index in range(10)])

    assert len(plan.sub_questions) == MAX_SUB_QUESTIONS


def test_plan_rejects_an_empty_list():
    with pytest.raises(ValidationError):
        ResearchPlan(sub_questions=[])


def test_plan_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ResearchPlan(sub_questions=["q"], extra="value")


# --- normalize_research_query ----------------------------------------------


def test_normalize_research_query_strips_a_string():
    assert normalize_research_query("  问题  ") == "问题"


@pytest.mark.parametrize("content", ["", "   ", []])
def test_normalize_research_query_rejects_empty_content(content):
    with pytest.raises(ValueError):
        normalize_research_query(content)


def test_normalize_research_query_rejects_unsupported_types():
    with pytest.raises(ValueError, match="must be a string"):
        normalize_research_query({"type": "text", "text": "x"})


# --- coerce_sub_questions ---------------------------------------------------


def test_coerce_accepts_a_research_plan():
    plan = ResearchPlan(sub_questions=["a", "b"])

    assert coerce_sub_questions(plan, "原始问题") == ["a", "b"]


def test_coerce_accepts_a_valid_dict():
    assert coerce_sub_questions({"sub_questions": ["a", "b"]}, "原始问题") == [
        "a",
        "b",
    ]


@pytest.mark.parametrize(
    "raw_plan",
    [
        {"sub_questions": []},
        {"sub_questions": ["   "]},
        {"unexpected": "shape"},
        None,
        "a string",
        ["a", "b"],
    ],
)
def test_coerce_degrades_to_the_original_question(raw_plan):
    assert coerce_sub_questions(raw_plan, "原始问题") == ["原始问题"]


# --- plan_research ----------------------------------------------------------


def test_plan_research_uses_the_latest_human_turn():
    from langchain_core.messages import AIMessage, HumanMessage

    planner = FakePlanner({"sub_questions": ["a", "b"]})

    update = plan_research(
        {
            "messages": [
                HumanMessage(content="旧问题"),
                AIMessage(content="旧回答"),
                HumanMessage(content="新问题"),
            ]
        },
        planner,
    )

    assert planner.received_payloads == [{"research_query": "新问题"}]
    assert update["research_query"] == "新问题"


def test_plan_research_requires_a_human_turn():
    from langchain_core.messages import AIMessage

    with pytest.raises(ValueError, match="HumanMessage"):
        plan_research({"messages": [AIMessage(content="answer")]}, FakePlanner({}))


def test_passthrough_planner_keeps_the_raw_question_intact():
    query = "第一段\n\n第二段"

    assert PassthroughPlanner().invoke({"research_query": query}) == {
        "sub_questions": [query]
    }
