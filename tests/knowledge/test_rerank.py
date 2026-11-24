"""Unit tests for the HTTP ``/rerank`` cross-encoder client and env configuration."""

from __future__ import annotations

import json
import math

import httpx
import pytest

from researchflow.knowledge.rerank import (
    DEFAULT_RERANK_CANDIDATES,
    DEFAULT_RERANK_TIMEOUT_SECONDS,
    HttpReranker,
    build_reranker,
    rerank_candidate_count,
)


def test_build_reranker_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RESEARCHFLOW_RERANK_MODEL", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_BASE_URL", raising=False)

    assert build_reranker() is None

    monkeypatch.setenv("RESEARCHFLOW_RERANK_MODEL", "   ")
    assert build_reranker() is None


def test_build_reranker_reuses_siliconflow_credentials_and_supports_overrides(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sf-key")
    monkeypatch.setenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1/")
    monkeypatch.delenv("RESEARCHFLOW_RERANK_API_KEY", raising=False)
    monkeypatch.delenv("RESEARCHFLOW_RERANK_BASE_URL", raising=False)
    monkeypatch.delenv("RESEARCHFLOW_RERANK_TIMEOUT_SECONDS", raising=False)

    reranker = build_reranker()
    assert isinstance(reranker, HttpReranker)
    assert reranker.model == "BAAI/bge-reranker-v2-m3"
    assert reranker.api_key == "sf-key"
    assert reranker.endpoint == "https://api.siliconflow.cn/v1/rerank"
    assert reranker.timeout == DEFAULT_RERANK_TIMEOUT_SECONDS

    monkeypatch.setenv("RESEARCHFLOW_RERANK_API_KEY", "override-key")
    monkeypatch.setenv("RESEARCHFLOW_RERANK_BASE_URL", "https://custom.example/v1")
    monkeypatch.setenv("RESEARCHFLOW_RERANK_TIMEOUT_SECONDS", "4.5")

    overridden = build_reranker()
    assert overridden is not None
    assert overridden.api_key == "override-key"
    assert overridden.endpoint == "https://custom.example/v1/rerank"
    assert overridden.timeout == pytest.approx(4.5)


def test_build_reranker_requires_credentials_when_model_is_enabled(monkeypatch):
    monkeypatch.setenv("RESEARCHFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
    monkeypatch.delenv("RESEARCHFLOW_RERANK_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.setenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

    with pytest.raises(ValueError, match="API_KEY"):
        build_reranker()

    monkeypatch.setenv("SILICONFLOW_API_KEY", "sf-key")
    monkeypatch.delenv("RESEARCHFLOW_RERANK_BASE_URL", raising=False)
    monkeypatch.delenv("SILICONFLOW_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="BASE_URL"):
        build_reranker()


def test_rerank_candidate_count_bounds_and_validation(monkeypatch):
    monkeypatch.delenv("RESEARCHFLOW_RERANK_CANDIDATES", raising=False)
    assert rerank_candidate_count(5) == DEFAULT_RERANK_CANDIDATES
    # Minimum is clamped to limit when limit exceeds the configured candidate pool.
    monkeypatch.setenv("RESEARCHFLOW_RERANK_CANDIDATES", "4")
    assert rerank_candidate_count(10) == 10

    monkeypatch.setenv("RESEARCHFLOW_RERANK_CANDIDATES", "100")
    assert rerank_candidate_count(5) == 100

    for invalid in ("abc", "0", "-5", "101"):
        monkeypatch.setenv("RESEARCHFLOW_RERANK_CANDIDATES", invalid)
        with pytest.raises(ValueError, match="RESEARCHFLOW_RERANK_CANDIDATES"):
            rerank_candidate_count(5)


def test_http_reranker_posts_expected_payload_and_orders_by_relevance_score():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "rerank-1",
                # Unsorted and with a score tie between indices 2 and 0.
                "results": [
                    {"index": 2, "relevance_score": 0.50},
                    {"index": 1, "relevance_score": 0.92},
                    {"index": 0, "relevance_score": 0.50},
                ],
            },
        )

    reranker = HttpReranker(
        model="BAAI/bge-reranker-v2-m3",
        api_key="secret-token",
        base_url="https://api.siliconflow.cn/v1/",
        transport=httpx.MockTransport(handler),
    )

    order = reranker.rerank(
        "default timeout",
        ["doc zero", "doc one", "doc two"],
        top_n=3,
    )

    assert captured["url"] == "https://api.siliconflow.cn/v1/rerank"
    assert captured["auth"] == "Bearer secret-token"
    assert captured["body"] == {
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "default timeout",
        "documents": ["doc zero", "doc one", "doc two"],
        "top_n": 3,
    }
    # Index 1 wins; indices 0 and 2 tie at 0.50 and fall back to original index order.
    assert order == [1, 0, 2]


def test_http_reranker_pads_missing_indices_in_original_order():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"index": 2, "relevance_score": 0.99}]},
        )

    reranker = HttpReranker(
        model="BAAI/bge-reranker-v2-m3",
        api_key="token",
        base_url="https://api.siliconflow.cn/v1",
        transport=httpx.MockTransport(handler),
    )

    assert reranker.rerank("q", ["a", "b", "c", "d"], top_n=3) == [2, 0, 1]
    assert reranker.rerank("q", [], top_n=3) == []
    assert reranker.rerank("q", ["a"], top_n=0) == []


@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (500, {"error": "internal"}),
        (200, []),
        (200, {"results": []}),
        (200, {"results": ["not-an-object"]}),
        (200, {"results": [{"index": 5, "relevance_score": 0.9}]}),
        (200, {"results": [{"index": -1, "relevance_score": 0.9}]}),
        (200, {"results": [{"index": True, "relevance_score": 0.9}]}),
        (
            200,
            {
                "results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.8},
                ]
            },
        ),
        (200, {"results": [{"index": 0, "relevance_score": True}]}),
    ],
)
def test_http_reranker_rejects_malformed_responses(status_code, body):
    reranker = HttpReranker(
        model="BAAI/bge-reranker-v2-m3",
        api_key="token",
        base_url="https://api.siliconflow.cn/v1",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(status_code, json=body)
        ),
    )

    with pytest.raises((httpx.HTTPStatusError, ValueError)):
        reranker.rerank("query", ["doc a", "doc b"], top_n=2)


def test_http_reranker_rejects_non_finite_scores():
    from researchflow.knowledge.rerank import _parse_rerank_response

    for bad_score in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="relevance_score"):
            _parse_rerank_response(
                {"results": [{"index": 0, "relevance_score": bad_score}]},
                document_count=1,
                top_n=1,
            )


def test_backend_reranker_dependency_returns_build_reranker(monkeypatch):
    from researchflow.backend.knowledge_dependencies import get_reranker_factory

    monkeypatch.delenv("RESEARCHFLOW_RERANK_MODEL", raising=False)
    factory = get_reranker_factory()
    assert factory is build_reranker
    assert factory() is None

