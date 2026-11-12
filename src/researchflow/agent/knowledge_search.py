from collections.abc import Callable
from uuid import UUID

import httpx
from langchain_core.tools import tool
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
)

from .evidence import ProjectDocumentProvenance, UserUploadEvidence


MAX_CONTEXT_RADIUS = 3

# The same threshold the retrieval evaluation uses to decide that nothing it
# returned is close enough to answer from. The Agent does not refuse here: it has
# a web tool and a writer that can qualify a claim. It marks the evidence instead,
# so the writer cannot present a weak match as support.
DEFAULT_ABSTAIN_THRESHOLD = 0.60
KNOWLEDGE_TIMEOUT_SECONDS = 10.0


class KnowledgeScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: UUID
    project_id: UUID


class KnowledgeHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: UUID
    chunk_id: UUID
    filename: StrictStr
    content: StrictStr
    score: StrictFloat = Field(allow_inf_nan=False)

    @field_validator("filename", "content")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Knowledge hit text cannot be empty")
        return value


class KnowledgeSearchError(RuntimeError):
    pass


_KNOWLEDGE_HITS_ADAPTER = TypeAdapter(list[KnowledgeHit])


class KnowledgeClient:
    def __init__(
        self,
        base_url: str,
        *,
        post: Callable[..., httpx.Response] = httpx.post,
        get: Callable[..., httpx.Response] = httpx.get,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            raise ValueError("Backend URL cannot be empty")
        self._base_url = normalized
        self._post = post
        self._get = get

    def search(
        self,
        *,
        scope: KnowledgeScope,
        query: str,
        limit: int,
    ) -> list[KnowledgeHit]:
        try:
            response = self._post(
                f"{self._base_url}/projects/{scope.project_id}/knowledge/search",
                headers={"X-ResearchFlow-User-Id": str(scope.user_id)},
                json={"query": query, "limit": limit},
                timeout=KNOWLEDGE_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                raise KnowledgeSearchError("Knowledge search unavailable")
            return _KNOWLEDGE_HITS_ADAPTER.validate_python(response.json())
        except KnowledgeSearchError:
            raise
        except (httpx.HTTPError, TypeError, ValueError):
            raise KnowledgeSearchError("Knowledge search unavailable") from None

    def context(
        self,
        *,
        scope: KnowledgeScope,
        chunk_id: str,
        radius: int,
    ) -> str:
        """Return the window around one chunk, or raise KnowledgeSearchError.

        The caller treats a failure as "use the chunk as retrieved": a window is
        an improvement, never a requirement.
        """

        try:
            response = self._get(
                f"{self._base_url}/projects/{scope.project_id}/knowledge/"
                f"chunks/{chunk_id}/context",
                headers={"X-ResearchFlow-User-Id": str(scope.user_id)},
                params={"radius": radius},
                timeout=KNOWLEDGE_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                raise KnowledgeSearchError("Chunk context unavailable")
            payload = response.json()
            content = payload.get("content") if isinstance(payload, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise KnowledgeSearchError("Chunk context unavailable")
            return content
        except KnowledgeSearchError:
            raise
        except (httpx.HTTPError, TypeError, ValueError):
            raise KnowledgeSearchError("Chunk context unavailable") from None


def build_knowledge_search_tool(
    *,
    scope: KnowledgeScope,
    client: KnowledgeClient,
    context_radius: int = 0,
    weak_match_threshold: float = DEFAULT_ABSTAIN_THRESHOLD,
):
    """Build the knowledge_search tool.

    ``context_radius`` widens every hit by that many chunks on each side. It is
    off by default because it changes what the Writer reads; the Product enables
    it with `RESEARCHFLOW_CONTEXT_RADIUS`. On the evaluation corpus the answer of
    an answerable case sits within two chunks of a returned hit in 95.6% of cases
    against 88.9% for the exact hit alone.
    """

    if not 0 <= context_radius <= MAX_CONTEXT_RADIUS:
        raise ValueError(f"context_radius must be between 0 and {MAX_CONTEXT_RADIUS}")
    if not isinstance(weak_match_threshold, (int, float)) or isinstance(
        weak_match_threshold, bool
    ):
        raise ValueError("weak_match_threshold must be a number")
    if not 0.0 <= weak_match_threshold <= 1.0:
        raise ValueError("weak_match_threshold must be between 0 and 1")

    scope = KnowledgeScope.model_validate(scope)

    @tool("knowledge_search")
    def knowledge_search(
        query: StrictStr,
        limit: StrictInt = 5,
    ) -> list[UserUploadEvidence]:
        """Search permanent Knowledge owned by the current Project."""

        query = query.strip()
        if not query or len(query) > 2000:
            raise ValueError("query must be a non-empty string")
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("limit must be an integer from 1 to 20")

        hits = client.search(scope=scope, query=query, limit=limit)

        best_score = max((hit.score for hit in hits), default=0.0)
        weak = bool(hits) and best_score < weak_match_threshold

        evidence: list[UserUploadEvidence] = []
        seen_content: set[str] = set()

        for hit in hits:
            content = hit.content
            note: str | None = None

            if context_radius > 0:
                try:
                    window = client.context(
                        scope=scope, chunk_id=str(hit.chunk_id), radius=context_radius
                    )
                except KnowledgeSearchError:
                    # A missing window must never lose the hit itself.
                    window = None
                if window is not None and window.strip():
                    content = window
                    note = f"expanded by {context_radius} chunks around the match"

            if content in seen_content:
                # Two windows can overlap heavily; one copy is enough.
                continue
            seen_content.add(content)

            if weak:
                warning = (
                    f"weak match: the best cosine similarity in this result is "
                    f"{best_score:.2f}, below the {weak_match_threshold:.2f} "
                    "threshold; treat this as context, not as support"
                )
                note = f"{note}; {warning}" if note else warning

            evidence.append(
                UserUploadEvidence(
                    source_label=hit.filename,
                    content=content,
                    retrieval_score=hit.score,
                    relevance_note=note,
                    provenance=ProjectDocumentProvenance(
                        document_id=hit.document_id,
                        chunk_id=hit.chunk_id,
                        filename=hit.filename,
                    ),
                )
            )

        return evidence

    return knowledge_search
