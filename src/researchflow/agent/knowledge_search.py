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
    ) -> None:
        normalized = base_url.rstrip("/")
        if not normalized:
            raise ValueError("Backend URL cannot be empty")
        self._base_url = normalized
        self._post = post

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


def build_knowledge_search_tool(
    *,
    scope: KnowledgeScope,
    client: KnowledgeClient,
):
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
        return [
            UserUploadEvidence(
                source_label=hit.filename,
                content=hit.content,
                retrieval_score=hit.score,
                provenance=ProjectDocumentProvenance(
                    document_id=hit.document_id,
                    chunk_id=hit.chunk_id,
                    filename=hit.filename,
                ),
            )
            for hit in hits
        ]

    return knowledge_search
