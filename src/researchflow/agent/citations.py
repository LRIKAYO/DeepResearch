from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictStr, TypeAdapter, field_validator

from .evidence import (
    ProjectDocumentProvenance,
    TemporaryWebProvenance,
    validate_evidence_list,
)


class CitationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: StrictStr = Field(pattern=r"^c[1-9][0-9]*$")
    source_label: StrictStr
    excerpt: StrictStr = Field(min_length=1, max_length=500)

    @field_validator("source_label", "excerpt")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Citation text cannot be empty")
        return value


class TemporaryResearchCitation(CitationModel):
    source_type: Literal["temporary_research"] = "temporary_research"
    provenance: TemporaryWebProvenance


class UserUploadCitation(CitationModel):
    source_type: Literal["user_upload"] = "user_upload"
    provenance: ProjectDocumentProvenance


Citation = Annotated[
    TemporaryResearchCitation | UserUploadCitation,
    Field(discriminator="source_type"),
]
CitationPayload: TypeAlias = dict[str, Any]

_CITATION_LIST_ADAPTER = TypeAdapter(list[Citation])


def validate_citation_list(value: object) -> list[CitationPayload]:
    models = _CITATION_LIST_ADAPTER.validate_python(value)
    return [model.model_dump(mode="json", exclude_none=True) for model in models]


def map_evidence_to_citations(value: object) -> list[CitationPayload]:
    evidence = validate_evidence_list(value)
    citations: list[Citation] = []
    for index, item in enumerate(evidence, start=1):
        common = {
            "citation_id": f"c{index}",
            "source_label": item["source_label"],
            "excerpt": _excerpt(item["content"]),
            "provenance": item["provenance"],
        }
        if item["source_type"] == "temporary_research":
            citations.append(TemporaryResearchCitation(**common))
        else:
            citations.append(UserUploadCitation(**common))
    return validate_citation_list(citations)


def _excerpt(content: str) -> str:
    normalized = content.strip()
    return normalized if len(normalized) <= 500 else normalized[:499] + "…"
