"""Cleaned Markdown (rag/data/processed/*.md) -> blocks with the heading path and the page of each block."""
import re
from dataclasses import dataclass

PAGE = re.compile(r"^<!-- page (\d+) -->$")
HEADING = re.compile(r"^(#{1,6})\s+(\S.*)$")


@dataclass
class Block:
    kind: str                      # 'heading' | 'text' | 'table'
    text: str                      # heading text without '#', a paragraph or list item, or table rows
    level: int = 0                 # heading level (1-6), 0 for other blocks
    path: tuple = ()               # titles of the headings above (for a heading: including itself)
    page: int | None = None        # page of the block (PDF only)


def words(text: str) -> int:
    return len(text.split())


def parse_blocks(md: str) -> list[Block]:
    blocks: list[Block] = []
    stack: list[tuple[int, str]] = []
    page = None
    for unit in re.split(r"\n{2,}", md.strip()):
        unit = unit.strip()
        if not unit:
            continue
        m = PAGE.match(unit)
        if m:
            page = int(m.group(1))
            continue
        h = HEADING.match(unit) if "\n" not in unit else None
        if h:
            level, text = len(h.group(1)), h.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))
            blocks.append(Block("heading", text, level, tuple(t for _, t in stack), page))
            continue
        blocks.append(Block("table" if unit.startswith("|") else "text", unit, 0, tuple(t for _, t in stack), page))
    return blocks
