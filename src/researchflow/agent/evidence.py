from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictStr,
    TypeAdapter,
    field_validator,
)


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TemporaryWebProvenance(EvidenceModel):
    url: AnyHttpUrl
    captured_at: datetime | None = None


class ProjectDocumentProvenance(EvidenceModel):
    document_id: UUID
    chunk_id: UUID
    filename: StrictStr
    page_number: int | None = Field(default=None, ge=1)
    section_path: tuple[StrictStr, ...] | None = None

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("filename cannot be empty")
        return value


class TemporaryResearchEvidence(EvidenceModel):
    source_type: Literal["temporary_research"] = "temporary_research"
    source_label: StrictStr
    content: StrictStr
    provenance: TemporaryWebProvenance
    relevance_note: StrictStr | None = None

    @field_validator("source_label", "content")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evidence text cannot be empty")
        return value


class UserUploadEvidence(EvidenceModel):
    source_type: Literal["user_upload"] = "user_upload"
    source_label: StrictStr
    content: StrictStr
    provenance: ProjectDocumentProvenance
    retrieval_score: StrictFloat = Field(allow_inf_nan=False)
    relevance_note: StrictStr | None = None

    @field_validator("source_label", "content")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Evidence text cannot be empty")
        return value


Evidence = Annotated[
    TemporaryResearchEvidence | UserUploadEvidence,
    Field(discriminator="source_type"),
]
EvidencePayload: TypeAlias = dict[str, Any]

_EVIDENCE_LIST_ADAPTER = TypeAdapter(list[Evidence])


def validate_evidence_list(value: object) -> list[EvidencePayload]:
    models = _EVIDENCE_LIST_ADAPTER.validate_python(value)
    return [model.model_dump(mode="json", exclude_none=True) for model in models]
