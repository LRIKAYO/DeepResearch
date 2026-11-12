"""Structure-aware Markdown chunking.

Two knobs, both environment-overridable so that ingestion, evaluation and the
dataset loader always agree on chunk boundaries:

``RESEARCHFLOW_CHUNK_CHARS``
    Maximum characters per chunk (default 2000).

``RESEARCHFLOW_CHUNK_OVERLAP``
    Characters of the previous chunk repeated at the start of the next one
    (default 0). Overlap keeps an answer that straddles a boundary reachable
    from either side.

Environment defaults are read once at import. A dataset's ``chunk_index``
labels are only meaningful under the settings that built it, so the evaluation
runner records and checks them.
"""

import os
import re
from dataclasses import dataclass


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


MAX_CHUNK_CHARS = _env_int("RESEARCHFLOW_CHUNK_CHARS", 2000, minimum=200, maximum=20000)
CHUNK_OVERLAP_CHARS = _env_int(
    "RESEARCHFLOW_CHUNK_OVERLAP", 0, minimum=0, maximum=MAX_CHUNK_CHARS // 2
)
# Kept for callers that referenced the old name.
OVERLONG_BLOCK_OVERLAP_CHARS = CHUNK_OVERLAP_CHARS

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
            current = _carry_over(current)

        if len(block.strip("\r\n")) > MAX_CHUNK_CHARS:
            if current:
                _append_chunk(chunks, current)
                current = ""
            _append_overlong_block(chunks, block)
        elif not current or len(current + block) <= MAX_CHUNK_CHARS:
            current += block
        else:
            _append_chunk(chunks, current)
            carried = _carry_over(current)
            current = (
                carried + block
                if carried and len(carried) + len(block) <= MAX_CHUNK_CHARS
                else block
            )

    if current:
        _append_chunk(chunks, current)

    return [ChunkDraft(index, content) for index, content in enumerate(chunks)]


def _carry_over(content: str) -> str:
    """Tail of a flushed chunk that becomes the head of the next one."""

    if CHUNK_OVERLAP_CHARS <= 0 or not content:
        return ""
    if len(content) <= CHUNK_OVERLAP_CHARS:
        return ""

    tail = content[-CHUNK_OVERLAP_CHARS:]
    newline = tail.find("\n")
    if -1 < newline < len(tail) - 40:
        tail = tail[newline + 1 :]

    tail = tail.strip("\r\n")
    return tail if len(tail) >= 40 else ""


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
    step = MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS
    if step <= 0:
        step = MAX_CHUNK_CHARS
    for start in range(0, len(content), step):
        _append_chunk(chunks, content[start : start + MAX_CHUNK_CHARS])
        if start + MAX_CHUNK_CHARS >= len(content):
            break


def _append_chunk(chunks: list[str], content: str) -> None:
    content = content.strip("\r\n")
    if content.strip():
        chunks.append(content)
