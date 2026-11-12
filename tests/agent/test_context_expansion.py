"""Context expansion: the knowledge_search tool widens a hit with its neighbours."""

from uuid import uuid4

import pytest

from researchflow.agent.knowledge_search import (
    KnowledgeClient,
    KnowledgeHit,
    KnowledgeScope,
    KnowledgeSearchError,
    MAX_CONTEXT_RADIUS,
    build_knowledge_search_tool,
)
from researchflow.agent.runtime import read_context_radius

SCOPE = KnowledgeScope(
    user_id="11111111-1111-1111-1111-111111111111",
    project_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
)


def hit(index: int = 0, chunk_id: str | None = None) -> KnowledgeHit:
    return KnowledgeHit(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="notes.md",
        content=f"chunk-{index} body",
        score=0.8,
    )


class FakeClient:
    """Records calls; returns a window per chunk id."""

    def __init__(self, hits, *, window="{chunk} + neighbours", context_error=None):
        self._hits = hits
        self._window = window
        self._context_error = context_error
        self.search_calls: list[dict] = []
        self.context_calls: list[dict] = []

    def search(self, *, scope, query, limit):
        self.search_calls.append({"scope": scope, "query": query, "limit": limit})
        return list(self._hits)

    def context(self, *, scope, chunk_id, radius):
        self.context_calls.append({"chunk_id": chunk_id, "radius": radius})
        if self._context_error is not None:
            raise self._context_error
        return self._window.format(chunk=self._hits[0].content)


def tool_for(client, *, radius):
    return build_knowledge_search_tool(scope=SCOPE, client=client, context_radius=radius)


# --- radius = 0 --------------------------------------------------------------


def test_no_context_call_when_expansion_is_off():
    first, second = hit(0), hit(1)
    client = FakeClient([first, second])

    evidence = tool_for(client, radius=0).invoke({"query": "q", "limit": 5})

    assert client.context_calls == []
    assert [item.content for item in evidence] == ["chunk-0 body", "chunk-1 body"]
    assert all(item.relevance_note is None for item in evidence)


# --- radius > 0 --------------------------------------------------------------


def test_expansion_replaces_the_content_and_records_a_note():
    client = FakeClient([hit(0)])

    evidence = tool_for(client, radius=2).invoke({"query": "q", "limit": 5})

    assert client.context_calls == [
        {"chunk_id": str(client._hits[0].chunk_id), "radius": 2}
    ]
    assert evidence[0].content == "chunk-0 body + neighbours"
    assert evidence[0].relevance_note == "expanded by 2 chunks around the match"


def test_expansion_keeps_the_matched_chunk_provenance():
    target = hit(0)
    client = FakeClient([target])

    evidence = tool_for(client, radius=1).invoke({"query": "q", "limit": 5})

    assert evidence[0].provenance.chunk_id == target.chunk_id
    assert evidence[0].provenance.document_id == target.document_id
    assert evidence[0].retrieval_score == target.score


def test_a_failed_window_falls_back_to_the_chunk():
    client = FakeClient([hit(0)], context_error=KnowledgeSearchError("down"))

    evidence = tool_for(client, radius=2).invoke({"query": "q", "limit": 5})

    assert evidence[0].content == "chunk-0 body"
    assert evidence[0].relevance_note is None


def test_identical_windows_are_collapsed():
    first, second = hit(0), hit(1)
    client = FakeClient([first, second], window="same window")

    evidence = tool_for(client, radius=2).invoke({"query": "q", "limit": 5})

    assert len(evidence) == 1
    assert client.context_calls and len(client.context_calls) == 2


@pytest.mark.parametrize("radius", [-1, MAX_CONTEXT_RADIUS + 1])
def test_out_of_range_radius_is_rejected(radius):
    with pytest.raises(ValueError, match="context_radius"):
        build_knowledge_search_tool(scope=SCOPE, client=FakeClient([]), context_radius=radius)


# --- client ------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_client_context_reads_the_window():
    calls = []

    def get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse(200, {"content": "window text"})

    client = KnowledgeClient("http://backend.test", get=get)

    content = client.context(scope=SCOPE, chunk_id="c-1", radius=2)

    assert content == "window text"
    assert calls[0]["url"] == (
        f"http://backend.test/projects/{SCOPE.project_id}/knowledge/chunks/c-1/context"
    )
    assert calls[0]["params"] == {"radius": 2}
    assert calls[0]["headers"]["X-ResearchFlow-User-Id"] == str(SCOPE.user_id)


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(404, None),
        FakeResponse(200, {}),
        FakeResponse(200, {"content": "   "}),
    ],
)
def test_client_context_rejects_unusable_answers(response):
    client = KnowledgeClient("http://backend.test", get=lambda *a, **k: response)

    with pytest.raises(KnowledgeSearchError):
        client.context(scope=SCOPE, chunk_id="c-1", radius=2)


# --- runtime knob ------------------------------------------------------------


def test_context_radius_defaults_to_two(monkeypatch):
    monkeypatch.delenv("RESEARCHFLOW_CONTEXT_RADIUS", raising=False)
    assert read_context_radius() == 2


@pytest.mark.parametrize("raw,expected", [("0", 0), ("1", 1), ("3", 3)])
def test_context_radius_reads_the_environment(monkeypatch, raw, expected):
    monkeypatch.setenv("RESEARCHFLOW_CONTEXT_RADIUS", raw)
    assert read_context_radius() == expected


@pytest.mark.parametrize("raw", ["-1", "4", "wide"])
def test_context_radius_rejects_bad_values(monkeypatch, raw):
    monkeypatch.setenv("RESEARCHFLOW_CONTEXT_RADIUS", raw)
    with pytest.raises(ValueError, match="RESEARCHFLOW_CONTEXT_RADIUS"):
        read_context_radius()

# --- weak evidence -----------------------------------------------------------


def test_weak_match_is_flagged_for_the_writer():
    weak = KnowledgeHit(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="notes.md",
        content="barely related",
        score=0.42,
    )
    client = FakeClient([weak])

    evidence = build_knowledge_search_tool(
        scope=SCOPE, client=client, context_radius=0
    ).invoke({"query": "q", "limit": 5})

    assert evidence[0].relevance_note is not None
    assert "weak match" in evidence[0].relevance_note
    assert "0.42" in evidence[0].relevance_note


def test_a_confident_match_carries_no_warning():
    client = FakeClient([hit(0)])  # score 0.8

    evidence = build_knowledge_search_tool(
        scope=SCOPE, client=client, context_radius=0
    ).invoke({"query": "q", "limit": 5})

    assert evidence[0].relevance_note is None


def test_expansion_and_weakness_share_one_note():
    weak = KnowledgeHit(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="notes.md",
        content="barely related",
        score=0.30,
    )
    client = FakeClient([weak])

    evidence = build_knowledge_search_tool(
        scope=SCOPE, client=client, context_radius=2
    ).invoke({"query": "q", "limit": 5})

    note = evidence[0].relevance_note or ""
    assert "expanded by 2 chunks" in note
    assert "weak match" in note


def test_an_empty_result_is_not_flagged_as_weak():
    client = FakeClient([])

    evidence = build_knowledge_search_tool(
        scope=SCOPE, client=client, context_radius=0
    ).invoke({"query": "q", "limit": 5})

    assert evidence == []


@pytest.mark.parametrize("threshold", [-0.1, 1.1, "high"])
def test_weak_threshold_is_validated(threshold):
    with pytest.raises(ValueError, match="weak_match_threshold"):
        build_knowledge_search_tool(
            scope=SCOPE, client=FakeClient([]), weak_match_threshold=threshold
        )
