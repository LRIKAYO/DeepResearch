import json
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from researchflow.agent.citations import (
    map_evidence_to_citations,
    validate_citation_list,
)
from researchflow.agent.evidence import (
    ProjectDocumentProvenance,
    TemporaryResearchEvidence,
    TemporaryWebProvenance,
    UserUploadEvidence,
)


def test_mapper_preserves_mixed_evidence_order_and_duplicates():
    captured_at = datetime(2026, 9, 14, 8, 30, tzinfo=timezone.utc)
    document_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    chunk_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    web = TemporaryResearchEvidence(
        source_label="Web source",
        content="  Web evidence  ",
        relevance_note="This diagnostic must not become a Citation field.",
        provenance=TemporaryWebProvenance(
            url="https://example.com/article?version=2#section",
            captured_at=captured_at,
        ),
    )
    upload = UserUploadEvidence(
        source_label="notes.md",
        content="Project evidence",
        retrieval_score=-0.75,
        provenance=ProjectDocumentProvenance(
            document_id=document_id,
            chunk_id=chunk_id,
            filename="notes.md",
            page_number=3,
            section_path=("Overview", "Evidence"),
        ),
    )

    citations = map_evidence_to_citations([web, upload, web])

    assert [item["citation_id"] for item in citations] == ["c1", "c2", "c3"]
    assert [item["source_type"] for item in citations] == [
        "temporary_research",
        "user_upload",
        "temporary_research",
    ]
    assert citations[0]["excerpt"] == "Web evidence"
    assert citations[0]["source_label"] == "Web source"
    assert citations[0]["provenance"] == {
        "url": "https://example.com/article?version=2#section",
        "captured_at": "2026-09-14T08:30:00Z",
    }
    assert citations[1]["provenance"] == {
        "document_id": str(document_id),
        "chunk_id": str(chunk_id),
        "filename": "notes.md",
        "page_number": 3,
        "section_path": ["Overview", "Evidence"],
    }
    assert citations[2] == {**citations[0], "citation_id": "c3"}
    for citation in citations:
        assert set(citation) == {
            "citation_id", "source_type", "source_label", "excerpt", "provenance"
        }
    assert validate_citation_list(json.loads(json.dumps(citations))) == citations
    assert map_evidence_to_citations([web, upload, web]) == citations
    assert map_evidence_to_citations([upload])[0]["citation_id"] == "c1"
    assert map_evidence_to_citations([]) == []


@pytest.mark.parametrize("length", [499, 500, 501])
def test_mapper_truncates_excerpt_at_500_unicode_code_points(length):
    content = ("证🔬" * 251)[:length]
    evidence = TemporaryResearchEvidence(
        source_label="Web source",
        content=" \n" + content + "\t ",
        provenance=TemporaryWebProvenance(url="https://example.com"),
    )

    citation = map_evidence_to_citations([evidence])[0]

    expected = content if length <= 500 else content[:499] + "…"
    assert citation["excerpt"] == expected
    assert len(citation["excerpt"]) == min(length, 500)


def test_mapper_preserves_internal_whitespace_and_source_label():
    evidence = TemporaryResearchEvidence(
        source_label="  Source label  ",
        content=" \nfirst  paragraph\n\nsecond\t段落\t ",
        provenance=TemporaryWebProvenance(url="https://example.com"),
    )

    citation = map_evidence_to_citations([evidence])[0]

    assert citation["source_label"] == evidence.source_label
    assert citation["excerpt"] == "first  paragraph\n\nsecond\t段落"
    assert citation["provenance"] == {"url": "https://example.com/"}


@pytest.mark.parametrize(
    "override",
    [
        {"citation_id": "c0"},
        {"citation_id": "c01"},
        {"citation_id": "c１"},
        {"citation_id": "c-1"},
        {"citation_id": 1},
        {"source_type": "saved_web"},
        {"source_label": " \t"},
        {"source_label": 42},
        {"excerpt": ""},
        {"excerpt": "\n\t"},
        {"excerpt": "x" * 501},
        {"excerpt": 42},
        {"retrieval_score": 0.9},
        {"relevance_note": "diagnostic only"},
        {"provenance": {"url": "file:///private.txt"}},
        {"provenance": {"url": "https://example.com", "score": 0.9}},
        {
            "provenance": {
                "document_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "chunk_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "filename": "notes.md",
            }
        },
    ],
)
def test_citation_contract_rejects_invalid_shape(override):
    citation = {
        "citation_id": "c1",
        "source_type": "temporary_research",
        "source_label": "Web source",
        "excerpt": "Evidence",
        "provenance": {"url": "https://example.com"},
    }

    with pytest.raises(ValidationError):
        validate_citation_list([{**citation, **override}])


def test_mapper_revalidates_evidence_payloads():
    with pytest.raises(ValidationError, match="source_type"):
        map_evidence_to_citations([{"source": "legacy", "content": "old"}])

    with pytest.raises(ValidationError, match="content"):
        map_evidence_to_citations(
            [{
                "source_type": "temporary_research",
                "source_label": "source",
                "content": 42,
                "provenance": {"url": "https://example.com"},
            }]
        )
