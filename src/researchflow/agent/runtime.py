import logging
import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.runnables.config import RunnableConfig
from langchain_openai import ChatOpenAI

from .citation_audit import audit_citations, citation_ids_for, detect_report_language
from .evidence import render_evidence_block
from .graph import (
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_MAX_TOOL_ROUNDS,
    MAX_TOOL_CALLS_LIMIT,
    MAX_TOOL_ROUNDS_LIMIT,
    build_graph,
)
from .knowledge_search import (
    DEFAULT_ABSTAIN_THRESHOLD,
    MAX_CONTEXT_RADIUS,
    KnowledgeClient,
)

DEFAULT_CONTEXT_RADIUS = 2
from .persistence import ReportPersister
from .plan import ResearchPlan
from .verification import VerificationBatch
from .web_search import build_web_search_tool


logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """\
You are the planning stage of a research agent.

Split the research question into 2 to 4 self-contained sub-questions that,
taken together, answer it. Good sub-questions are searchable: each names the
entity, the property and the kind of evidence that would settle it.

Rules:
- Cover different angles (definition, mechanism, comparison, timeline,
  counter-evidence) instead of restating the question in different words.
- Never add sub-questions that need information the sources cannot contain.
- Write the sub-questions in the same language as the research question.
"""

RESEARCHER_SYSTEM_PROMPT = """\
You are the researcher in a bounded, multi-round investigation.

You can call two tools:
- knowledge_search: searches the user's private Project documents. Prefer it for
  facts that live inside the project.
- web_search: searches the public web. Use it for external, recent or
  cross-checking facts.

How to work:
- Read the research sub-questions and the evidence collected so far.
- Identify the single most important gap, then issue the smallest number of
  focused tool calls that closes it.
- The tool-round budget is enforced by the system. When it is exhausted you can
  no longer search, so spend it on the questions that matter most.
- When the evidence already answers the question, stop calling tools and reply
  with exactly READY. Do not repeat searches you have already run.
- Never invent sources, quotations, numbers or URLs.
"""

WRITER_SYSTEM_PROMPT = """\
You are a research report writer.

You receive a research question, its sub-questions, and a numbered list of
evidence where each item starts with an id such as [c1].

Write a concise, well-structured report:
- Organise the report by the sub-questions. Use Markdown headings.
- Every sentence that states a fact must carry the ids of the evidence items
  that support it, for example [c1] or [c1][c3]. No factual sentence without a
  marker.
- **Every id in the evidence list must appear at least once in the report body.**
  The evidence list is an inventory of what was retrieved, so an unused id means
  an unused source; if a source turned out to be irrelevant, say so in one
  sentence and cite it there instead of leaving it unreferenced.
- When the evidence does not answer a sub-question, say so in one sentence and
  cite the evidence you inspected. "Not documented" is a finding and needs a
  marker just like any other claim.
- Only use ids that appear in the evidence list. Never invent an id, source,
  number or quotation.
- If no evidence supports a claim you believe matters, still state it but mark
  it as unverified using `[unverified]` in an English report or `[未证实]` in a
  Chinese one.
- Prefer specific facts, figures and dates over generic summary sentences.
- Write the report in {report_language}. The evidence is usually English; that is
  not a reason to switch language.
"""

WRITER_REPAIR_SYSTEM_PROMPT = """\
You repair the citation coverage of a research report you did not write.

You receive the research question, the numbered evidence list, a draft report,
and the ids that are listed as sources but never appear in the draft body.

Rewrite the draft so that:
- Every id in that missing list appears at least once, attached to the sentence
  it actually supports. If an id supports nothing, attach it to one sentence that
  says the source was consulted and did not settle the question.
- Every factual sentence keeps a marker. Add markers where they are missing.
- Nothing else changes: same structure, same findings, same language, no new
  facts, no invented ids or quotations.

Return only the corrected report, with no preamble and no commentary.
"""

VERIFIER_SYSTEM_PROMPT = """\
You verify citations in a research report.
For each item you receive a claim sentence and the passage it cites. Decide
whether the passage actually supports the claim:
- "full": the passage states what the claim says, or directly entails it.
- "partial": the passage is related and supports part of the claim, but a
  material part of the claim is not covered.
- "none": the passage does not support the claim, contradicts it, or is merely
  topically related.

Be strict. Shared vocabulary is not support. Return one verdict per item, using
the exact citation id you were given. Give a reason of at most 25 words quoting
or pointing at the decisive part of the passage.
"""


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def create_model() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=require_env("SILICONFLOW_API_KEY"),
        base_url=require_env("SILICONFLOW_BASE_URL"),
        model=require_env("SILICONFLOW_MODEL"),
        temperature=0,
    )


def create_web_search():
    return build_web_search_tool(api_key=require_env("TAVILY_API_KEY"))


def create_knowledge_client() -> KnowledgeClient:
    return KnowledgeClient(require_env("RESEARCHFLOW_BACKEND_URL"))


def create_report_persister() -> ReportPersister:
    return ReportPersister(require_env("RESEARCHFLOW_BACKEND_URL"))


def create_planner(model: Runnable) -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", PLANNER_SYSTEM_PROMPT),
            ("human", "Research question:\n{research_query}"),
        ]
    )
    return prompt | model.with_structured_output(ResearchPlan)


def _writer_inputs(payload: dict) -> dict:
    """Render a writer payload into prompt variables."""

    sub_questions = payload.get("sub_questions") or []
    if isinstance(sub_questions, list) and sub_questions:
        rendered_questions = "\n".join(
            f"{index}. {question}"
            for index, question in enumerate(sub_questions, start=1)
        )
    else:
        rendered_questions = "(none)"

    research_query = payload.get("research_query") or ""

    return {
        "research_query": research_query,
        "sub_questions": rendered_questions,
        "evidence": render_evidence_block(payload.get("evidence")),
        "report_language": detect_report_language(research_query),
    }


class _WriterWithCitationAudit:
    """Writer that checks its own citation coverage and repairs it once.

    The evidence inventory lists every retrieved passage, so a report that cites
    a few of them still publishes all of them. This wrapper audits the draft and,
    when ids are listed but never cited, asks for exactly one rewrite that adds
    the missing markers without changing the facts. A failed or unhelpful repair
    keeps the original draft: a report is never lost to a formatting fix.
    """

    def __init__(self, draft: Runnable, repair: Runnable) -> None:
        self._draft = draft
        self._repair = repair

    def invoke(self, payload: dict) -> str:
        evidence = payload.get("evidence") or []
        inputs = _writer_inputs(payload)

        report = self._draft.invoke(inputs)
        if not isinstance(report, str):
            raise ValueError("writer must return a string report")

        ids = citation_ids_for(len(evidence))
        before = audit_citations(report, ids)
        if before.complete or not ids:
            return report

        try:
            repaired = self._repair.invoke(
                {**inputs, "report": report, "missing": before.missing_list}
            )
        except Exception:
            logger.warning("citation repair pass failed; keeping the draft", exc_info=True)
            return report

        if not isinstance(repaired, str) or not repaired.strip():
            return report

        after = audit_citations(repaired, ids)
        logger.info(
            "citation repair: uncited %d -> %d", len(before.uncited), len(after.uncited)
        )
        if len(after.uncited) < len(before.uncited):
            return repaired

        return report


def create_writer(model: Runnable) -> Runnable:
    draft_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", WRITER_SYSTEM_PROMPT),
            (
                "human",
                """
Research question:
{research_query}

Sub-questions:
{sub_questions}

Evidence:
{evidence}

Generate the final research report.
""",
            ),
        ]
    )
    repair_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", WRITER_REPAIR_SYSTEM_PROMPT),
            (
                "human",
                """
Research question:
{research_query}

Sub-questions:
{sub_questions}

Evidence:
{evidence}

Draft report:
{report}

Citation ids that are listed but never cited in the draft:
{missing}
""",
            ),
        ]
    )

    draft = draft_prompt | model | StrOutputParser()
    repair = repair_prompt | model | StrOutputParser()
    return _WriterWithCitationAudit(draft, repair)


class _VerifierRunnable:
    """Renders verification items into a prompt and returns a VerificationBatch."""

    def __init__(self, model: Runnable) -> None:
        self._chain = (
            ChatPromptTemplate.from_messages(
                [
                    ("system", VERIFIER_SYSTEM_PROMPT),
                    ("human", "Items to verify:\n\n{items}"),
                ]
            )
            | model.with_structured_output(VerificationBatch)
        )

    def invoke(self, payload: dict):
        items = payload.get("items") or []
        rendered = "\n\n".join(
            "\n".join(
                [
                    f"citation_id: {item.get('citation_id', '')}",
                    f"claim: {item.get('claim', '')}",
                    f"source: {item.get('source', '')}",
                    f"passage: {item.get('passage', '')}",
                ]
            )
            for item in items
        )
        return self._chain.invoke({"items": rendered or "(none)"})


def create_verifier(model: Runnable) -> _VerifierRunnable:
    return _VerifierRunnable(model)


def read_max_tool_rounds() -> int:
    raw = os.getenv("RESEARCHFLOW_MAX_TOOL_ROUNDS", str(DEFAULT_MAX_TOOL_ROUNDS)).strip()
    if not raw:
        return DEFAULT_MAX_TOOL_ROUNDS
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            "RESEARCHFLOW_MAX_TOOL_ROUNDS must be an integer"
        ) from None
    if not 1 <= value <= MAX_TOOL_ROUNDS_LIMIT:
        raise ValueError(
            f"RESEARCHFLOW_MAX_TOOL_ROUNDS must be between 1 and {MAX_TOOL_ROUNDS_LIMIT}"
        )
    return value


def read_max_tool_calls() -> int:
    raw = os.getenv("RESEARCHFLOW_MAX_TOOL_CALLS", str(DEFAULT_MAX_TOOL_CALLS)).strip()
    if not raw:
        return DEFAULT_MAX_TOOL_CALLS
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            "RESEARCHFLOW_MAX_TOOL_CALLS must be an integer"
        ) from None
    if not 1 <= value <= MAX_TOOL_CALLS_LIMIT:
        raise ValueError(
            f"RESEARCHFLOW_MAX_TOOL_CALLS must be between 1 and {MAX_TOOL_CALLS_LIMIT}"
        )
    return value


def read_context_radius() -> int:
    raw = os.getenv("RESEARCHFLOW_CONTEXT_RADIUS", str(DEFAULT_CONTEXT_RADIUS)).strip()
    if not raw:
        return DEFAULT_CONTEXT_RADIUS
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("RESEARCHFLOW_CONTEXT_RADIUS must be an integer") from None
    if not 0 <= value <= MAX_CONTEXT_RADIUS:
        raise ValueError(
            f"RESEARCHFLOW_CONTEXT_RADIUS must be between 0 and {MAX_CONTEXT_RADIUS}"
        )
    return value


def read_weak_match_threshold() -> float:
    """Cosine similarity below which a knowledge result is flagged as weak."""

    raw = os.getenv(
        "RESEARCHFLOW_ABSTAIN_THRESHOLD", str(DEFAULT_ABSTAIN_THRESHOLD)
    ).strip()
    if not raw:
        return DEFAULT_ABSTAIN_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("RESEARCHFLOW_ABSTAIN_THRESHOLD must be a number") from None
    if not 0.0 <= value <= 1.0:
        raise ValueError("RESEARCHFLOW_ABSTAIN_THRESHOLD must be between 0 and 1")
    return value


def create_runtime(config: RunnableConfig | None = None):
    """Build the graph registered by the LangGraph Server."""
    model = create_model()
    return build_graph(
        researcher_model=model,
        web_tool=create_web_search(),
        knowledge_client=create_knowledge_client(),
        writer_impl=create_writer(model),
        planner_impl=create_planner(model),
        verifier_impl=create_verifier(model),
        persist_impl=create_report_persister(),
        max_tool_rounds=read_max_tool_rounds(),
        max_tool_calls=read_max_tool_calls(),
        context_radius=read_context_radius(),
        weak_match_threshold=read_weak_match_threshold(),
        recover_tool_errors=True,
        researcher_system_prompt=RESEARCHER_SYSTEM_PROMPT,
    )
