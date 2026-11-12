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


MAX_RENDERED_EVIDENCE_CHARS = 1500


def render_evidence_block(evidence: object) -> str:
    """Render Evidence as the numbered ``[cN]`` block prompts and reports share.

    The numbers must match ``map_evidence_to_citations``: citation ids are
    assigned by list position, so both sides must read the same ordered list.
    """

    if not isinstance(evidence, list) or not evidence:
        return "(no evidence collected yet)"

    blocks: list[str] = []

    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            continue

        source_label = str(item.get("source_label") or "unknown source")
        source_type = item.get("source_type")

        if source_type == "user_upload":
            provenance = item.get("provenance") or {}
            filename = provenance.get("filename") if isinstance(provenance, dict) else None
            if isinstance(filename, str) and filename and filename != source_label:
                source_label = f"{filename} ({source_label})"

        content = str(item.get("content") or "").strip()
        if len(content) > MAX_RENDERED_EVIDENCE_CHARS:
            content = content[: MAX_RENDERED_EVIDENCE_CHARS - 1] + "…"

        blocks.append(f"[c{index}] {source_label}\n{content}")

    return "\n\n".join(blocks) if blocks else "(no evidence collected yet)"

