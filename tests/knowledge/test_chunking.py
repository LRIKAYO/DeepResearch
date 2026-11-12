import pytest

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


def test_chunk_markdown_respects_a_smaller_max(monkeypatch):
    import researchflow.knowledge.chunking as chunking

    monkeypatch.setattr(chunking, "MAX_CHUNK_CHARS", 300)
    monkeypatch.setattr(chunking, "CHUNK_OVERLAP_CHARS", 0)

    text = "\n\n".join(f"## Section {i}\n\n" + ("word " * 60) for i in range(4))
    chunks = chunking.chunk_markdown(text)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 300 for chunk in chunks)


def test_chunk_markdown_repeats_a_tail_when_overlap_is_set(monkeypatch):
    import researchflow.knowledge.chunking as chunking

    monkeypatch.setattr(chunking, "MAX_CHUNK_CHARS", 300)
    monkeypatch.setattr(chunking, "CHUNK_OVERLAP_CHARS", 80)

    body = "".join(f"line {i} of the section\n" for i in range(30))
    text = "## A\n\n" + body + "\n## B\n\n" + body
    chunks = chunking.chunk_markdown(text)

    assert len(chunks) > 2
    overlaps = 0
    for previous, following in zip(chunks, chunks[1:]):
        tail = previous.content[-40:]
        if tail and tail in following.content:
            overlaps += 1
    assert overlaps >= 1


def test_env_int_rejects_a_bad_value(monkeypatch):
    import researchflow.knowledge.chunking as chunking

    monkeypatch.setenv("TEST_CHUNK_KNOB", "not-a-number")
    with pytest.raises(ValueError, match="TEST_CHUNK_KNOB"):
        chunking._env_int("TEST_CHUNK_KNOB", 10, minimum=1, maximum=20)

    monkeypatch.setenv("TEST_CHUNK_KNOB", "99")
    with pytest.raises(ValueError, match="between"):
        chunking._env_int("TEST_CHUNK_KNOB", 10, minimum=1, maximum=20)


def test_env_int_falls_back_to_the_default(monkeypatch):
    import researchflow.knowledge.chunking as chunking

    monkeypatch.delenv("TEST_CHUNK_KNOB", raising=False)
    assert chunking._env_int("TEST_CHUNK_KNOB", 7, minimum=1, maximum=20) == 7
