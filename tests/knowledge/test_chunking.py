from researchflow.knowledge.chunking import (
    MAX_CHUNK_CHARS,
    OVERLONG_BLOCK_OVERLAP_CHARS,
    ChunkDraft,
    chunk_markdown,
)


def test_heading_sections_define_chunk_boundaries():
    markdown = "# Overview\n\nIntro.\n\n## Details\n\nFact one.\n\nFact two."

    assert chunk_markdown(markdown) == [
        ChunkDraft(0, "# Overview\n\nIntro."),
        ChunkDraft(1, "## Details\n\nFact one.\n\nFact two."),
    ]


def test_paragraphs_pack_without_crossing_maximum():
    markdown = "First paragraph.\n\nSecond paragraph."

    assert chunk_markdown(markdown) == [ChunkDraft(0, markdown)]


def test_only_an_overlong_structural_block_uses_overlap():
    markdown = "A" * MAX_CHUNK_CHARS + "B"

    assert chunk_markdown(markdown) == [
        ChunkDraft(0, "A" * MAX_CHUNK_CHARS),
        ChunkDraft(1, "A" * OVERLONG_BLOCK_OVERLAP_CHARS + "B"),
    ]


def test_markdown_fence_hides_heading_syntax():
    markdown = "```md\n# not a section\n```\n\nAfter fence."

    assert chunk_markdown(markdown) == [ChunkDraft(0, markdown)]


def test_whitespace_only_input_emits_no_chunks():
    assert chunk_markdown(" \r\n\t\r\n") == []


def test_chunking_is_deterministic_with_consecutive_indexes():
    markdown = "# One\n\nText.\n\n# Two\n\nMore text."

    first = chunk_markdown(markdown)

    assert chunk_markdown(markdown) == first
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
