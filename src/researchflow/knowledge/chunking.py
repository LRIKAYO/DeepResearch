import re
from dataclasses import dataclass


MAX_CHUNK_CHARS = 2000
OVERLONG_BLOCK_OVERLAP_CHARS = 200

_ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]+|$)")
_SETEXT_HEADING = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    content: str


def chunk_markdown(text: str) -> list[ChunkDraft]:
    chunks: list[str] = []
    current = ""

    for block, starts_section in _structural_blocks(text):
        if starts_section and current:
            _append_chunk(chunks, current)
            current = ""

        if len(block.strip("\r\n")) > MAX_CHUNK_CHARS:
            if current:
                _append_chunk(chunks, current)
                current = ""
            _append_overlong_block(chunks, block)
        elif not current or len(current + block) <= MAX_CHUNK_CHARS:
            current += block
        else:
            _append_chunk(chunks, current)
            current = block

    if current:
        _append_chunk(chunks, current)

    return [ChunkDraft(index, content) for index, content in enumerate(chunks)]


def _structural_blocks(text: str) -> list[tuple[str, bool]]:
    blocks: list[tuple[str, bool]] = []
    lines: list[str] = []
    starts_section = False
    section_has_body = False
    fence_marker: str | None = None

    def flush() -> None:
        nonlocal lines, starts_section, section_has_body
        if lines:
            blocks.append(("".join(lines), starts_section))
        lines = []
        starts_section = False
        section_has_body = False

    for line in text.splitlines(keepends=True):
        stripped = line.strip("\r\n")
        fence = _FENCE.match(stripped)
        if fence_marker:
            lines.append(line)
            if fence and fence.group(1)[0] == fence_marker:
                fence_marker = None
            continue
        if fence:
            fence_marker = fence.group(1)[0]
            lines.append(line)
            section_has_body = True
            continue
        if _ATX_HEADING.match(stripped):
            flush()
            lines.append(line)
            starts_section = True
            continue
        if _SETEXT_HEADING.match(stripped) and lines:
            lines.append(line)
            starts_section = True
            section_has_body = False
            continue
        if not stripped.strip():
            if not lines:
                continue
            lines.append(line)
            if not starts_section or section_has_body:
                flush()
            continue
        lines.append(line)
        if starts_section:
            section_has_body = True

    flush()
    return blocks


def _append_overlong_block(chunks: list[str], block: str) -> None:
    content = block.strip("\r\n")
    step = MAX_CHUNK_CHARS - OVERLONG_BLOCK_OVERLAP_CHARS
    for start in range(0, len(content), step):
        _append_chunk(chunks, content[start : start + MAX_CHUNK_CHARS])
        if start + MAX_CHUNK_CHARS >= len(content):
            break


def _append_chunk(chunks: list[str], content: str) -> None:
    content = content.strip("\r\n")
    if content.strip():
        chunks.append(content)
