"""Pluggable cross-encoder reranker over HTTP ``/rerank`` endpoints.

The reranker reorders a small RRF candidate pool (top 20 by default) with a
cross-encoder such as ``BAAI/bge-reranker-v2-m3`` served behind a Cohere /
SiliconFlow-compatible ``POST {base_url}/rerank`` endpoint.

Two invariants keep this optional stage safe for existing callers and tests:

1. **Disabled by default.** Unless ``RESEARCHFLOW_RERANK_MODEL`` is explicitly
   set (or a ``Reranker`` is injected), ``build_reranker()`` returns ``None``
   and retrieval makes zero extra network calls.
2. **Order only, never score.** ``Reranker.rerank`` returns candidate *indices*,
   not relevance logits. ``search_knowledge`` still populates
   ``KnowledgeHit.score`` with the chunk's exact cosine similarity so the
   downstream ``0.60`` cosine abstention threshold stays calibrated.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

import httpx


DEFAULT_RERANK_CANDIDATES = 20
MAX_RERANK_CANDIDATES = 100
DEFAULT_RERANK_TIMEOUT_SECONDS = 8.0


class Reranker(Protocol):
    """Reorders ``documents`` for ``query`` and returns up to ``top_n`` indices."""

    def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> list[int]: ...


def rerank_candidate_count(limit: int) -> int:
    """Resolve ``RESEARCHFLOW_RERANK_CANDIDATES`` bounded to ``[limit, 100]``."""

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    raw = os.getenv("RESEARCHFLOW_RERANK_CANDIDATES", "").strip()
    if not raw:
        configured = DEFAULT_RERANK_CANDIDATES
    else:
        try:
            configured = int(raw)
        except ValueError as exc:
            raise ValueError(
                f"RESEARCHFLOW_RERANK_CANDIDATES must be an integer, got {raw!r}"
            ) from exc
        if not 1 <= configured <= MAX_RERANK_CANDIDATES:
            raise ValueError(
                f"RESEARCHFLOW_RERANK_CANDIDATES={configured} must be between "
                f"1 and {MAX_RERANK_CANDIDATES}"
            )

    return min(MAX_RERANK_CANDIDATES, max(limit, configured))


def _rerank_timeout_seconds() -> float:
    raw = os.getenv("RESEARCHFLOW_RERANK_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_RERANK_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"RESEARCHFLOW_RERANK_TIMEOUT_SECONDS must be numeric, got {raw!r}"
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("RESEARCHFLOW_RERANK_TIMEOUT_SECONDS must be positive and finite")
    return timeout


@dataclass(frozen=True)
class HttpReranker:
    """HTTP client for SiliconFlow / Cohere-compatible ``/rerank`` endpoints."""

    model: str
    api_key: str
    base_url: str
    timeout: float = DEFAULT_RERANK_TIMEOUT_SECONDS
    transport: httpx.BaseTransport | None = None

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/rerank"

    def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ) -> list[int]:
        if not documents or top_n < 1:
            return []

        effective_top_n = min(top_n, len(documents))
        payload = {
            "model": self.model,
            "query": query,
            "documents": list(documents),
            "top_n": effective_top_n,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            response = client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()

        return _parse_rerank_response(
            body,
            document_count=len(documents),
            top_n=effective_top_n,
        )


def _parse_rerank_response(
    body: Any,
    *,
    document_count: int,
    top_n: int,
) -> list[int]:
    if not isinstance(body, dict):
        raise ValueError("Rerank response body must be a JSON object")

    results = body.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("Rerank response must contain a non-empty 'results' list")

    seen: set[int] = set()
    scored: list[tuple[int, float]] = []
    for entry in results:
        if not isinstance(entry, dict):
            raise ValueError("Each rerank result entry must be an object")

        index = entry.get("index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < document_count
        ):
            raise ValueError(f"Invalid rerank candidate index: {index!r}")
        if index in seen:
            raise ValueError(f"Duplicate rerank candidate index: {index}")

        score = entry.get("relevance_score")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
        ):
            raise ValueError(f"Invalid rerank relevance_score: {score!r}")

        seen.add(index)
        scored.append((index, float(score)))

    # Ties break by input candidate index, which is already in RRF order.
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    ordered = [index for index, _ in scored]
    if len(ordered) < top_n:
        ordered.extend(index for index in range(document_count) if index not in seen)
    return ordered[:top_n]


def build_reranker() -> HttpReranker | None:
    """Build the configured HTTP reranker, or ``None`` when disabled."""

    model = os.getenv("RESEARCHFLOW_RERANK_MODEL", "").strip()
    if not model:
        return None

    api_key = (
        os.getenv("RESEARCHFLOW_RERANK_API_KEY")
        or os.getenv("SILICONFLOW_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise ValueError(
            "Missing required environment variable: "
            "RESEARCHFLOW_RERANK_API_KEY or SILICONFLOW_API_KEY"
        )

    base_url = (
        os.getenv("RESEARCHFLOW_RERANK_BASE_URL")
        or os.getenv("SILICONFLOW_BASE_URL")
        or ""
    ).strip()
    if not base_url:
        raise ValueError(
            "Missing required environment variable: "
            "RESEARCHFLOW_RERANK_BASE_URL or SILICONFLOW_BASE_URL"
        )

    return HttpReranker(
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=_rerank_timeout_seconds(),
    )
