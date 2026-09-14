from uuid import uuid4

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import ValidationError

from researchflow.agent.evidence import (
    ProjectDocumentProvenance,
    TemporaryResearchEvidence,
    TemporaryWebProvenance,
    UserUploadEvidence,
    validate_evidence_list,
)


def test_shared_validator_accepts_both_approved_evidence_variants():
    temporary = TemporaryResearchEvidence(
        source_label="Example",
        content="Temporary result",
        provenance=TemporaryWebProvenance(url="https://example.com"),
    )
    uploaded = UserUploadEvidence(
        source_label="notes.md",
        content="Permanent result",
        retrieval_score=0.75,
        provenance=ProjectDocumentProvenance(
            document_id=uuid4(),
            chunk_id=uuid4(),
            filename="notes.md",
        ),
    )

    validated = validate_evidence_list([temporary, uploaded])

    assert [item["source_type"] for item in validated] == [
        "temporary_research",
        "user_upload",
    ]
    assert validated[1]["provenance"]["document_id"] == str(
        uploaded.provenance.document_id
    )
    serializer = JsonPlusSerializer()
    assert serializer.loads_typed(serializer.dumps_typed(validated)) == validated


def test_shared_validator_rejects_legacy_evidence_shape():
    with pytest.raises(ValidationError, match="source_type"):
        validate_evidence_list([{"source": "legacy", "content": "old"}])
