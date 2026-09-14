from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from researchflow.agent.evidence import UserUploadEvidence
from researchflow.agent.knowledge_search import (
    KNOWLEDGE_TIMEOUT_SECONDS,
    KnowledgeClient,
    KnowledgeScope,
    KnowledgeSearchError,
    build_knowledge_search_tool,
)


def scope() -> KnowledgeScope:
    return KnowledgeScope(user_id=uuid4(), project_id=uuid4())


class RecordingPost:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def response(payload, status_code=200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def valid_hit(document_id=None, chunk_id=None):
    return {
        "document_id": str(document_id or uuid4()),
        "chunk_id": str(chunk_id or uuid4()),
        "filename": "notes.md",
        "content": "Permanent Project evidence.",
        "score": 0.82,
    }


def test_tool_hides_scope_and_maps_knowledge_hit_to_evidence():
    knowledge_scope = scope()
    document_id = uuid4()
    chunk_id = uuid4()
    post = RecordingPost(response([valid_hit(document_id, chunk_id)]))
    tool = build_knowledge_search_tool(
        scope=knowledge_scope,
        client=KnowledgeClient("http://backend.test/", post=post),
    )

    result = tool.invoke({"query": "  target  ", "limit": 3})

    assert set(tool.args_schema.model_json_schema()["properties"]) == {
        "query",
        "limit",
    }
    assert result == [
        UserUploadEvidence(
            source_label="notes.md",
            content="Permanent Project evidence.",
            retrieval_score=0.82,
            provenance={
                "document_id": document_id,
                "chunk_id": chunk_id,
                "filename": "notes.md",
            },
        )
    ]
    assert post.calls == [
        (
            f"http://backend.test/projects/{knowledge_scope.project_id}/knowledge/search",
            {
                "headers": {
                    "X-ResearchFlow-User-Id": str(knowledge_scope.user_id)
                },
                "json": {"query": "target", "limit": 3},
                "timeout": KNOWLEDGE_TIMEOUT_SECONDS,
            },
        )
    ]


def test_valid_empty_backend_result_returns_empty_evidence():
    tool = build_knowledge_search_tool(
        scope=scope(),
        client=KnowledgeClient(
            "http://backend.test",
            post=RecordingPost(response([])),
        ),
    )

    assert tool.invoke({"query": "nothing"}) == []


def test_string_score_is_sanitized_without_retry():
    post = RecordingPost(
        response(
            [
                {
                    **valid_hit(),
                    "score": "0.82",
                }
            ]
        )
    )

    tool = build_knowledge_search_tool(
        scope=scope(),
        client=KnowledgeClient(
            "http://backend.test",
            post=post,
        ),
    )

    with pytest.raises(KnowledgeSearchError) as error:
        tool.invoke(
            {
                "query": "target",
            }
        )

    assert str(error.value) == "Knowledge search unavailable"
    assert len(post.calls) == 1


def test_scope_is_frozen_and_rejects_unknown_fields():
    knowledge_scope = scope()

    with pytest.raises(ValidationError, match="frozen"):
        knowledge_scope.project_id = uuid4()
    with pytest.raises(ValidationError, match="extra_forbidden"):
        KnowledgeScope.model_validate(
            {
                "user_id": uuid4(),
                "project_id": uuid4(),
                "query": "model-controlled scope",
            }
        )


@pytest.mark.parametrize(
    "post",
    [
        RecordingPost(response({"detail": "Project not found"}, status_code=404)),
        RecordingPost(httpx.Response(200, content=b"not-json")),
        RecordingPost(response([{"document_id": "invalid"}])),
        RecordingPost(error=httpx.ReadTimeout("provider detail")),
    ],
    ids=["status", "json", "schema", "timeout"],
)
def test_client_failures_are_sanitized_without_retry(post):
    tool = build_knowledge_search_tool(
        scope=scope(),
        client=KnowledgeClient("http://backend.test", post=post),
    )

    with pytest.raises(KnowledgeSearchError) as error:
        tool.invoke({"query": "target"})

    assert str(error.value) == "Knowledge search unavailable"
    assert len(post.calls) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "   "},
        {"query": "x" * 2001},
        {"query": "valid", "limit": 0},
        {"query": "valid", "limit": 21},
        {"query": "valid", "limit": True},
    ],
    ids=["empty", "long", "limit-low", "limit-high", "limit-bool"],
)
def test_tool_rejects_invalid_model_arguments_before_http(arguments):
    post = RecordingPost(response([]))
    tool = build_knowledge_search_tool(
        scope=scope(),
        client=KnowledgeClient("http://backend.test", post=post),
    )

    with pytest.raises((ValueError, ValidationError)):
        tool.invoke(arguments)

    assert post.calls == []
