"""Structure-aware chunking: chunks follow the sections of a document.

A chunk is made of blocks of one section (or of a few tiny sibling sections), about TARGET words, never more than MAX
(except one unsplittable block). A heading always stays with the text below it. A long section is cut between paragraphs;
the continuation starts with the last paragraph of the previous chunk (the overlap). Between sections there is no overlap.
"""
import re
from dataclasses import dataclass, replace

from .blocks import Block, words

TARGET, MAX, MIN, OVERLAP_MAX = 300, 400, 60, 60


@dataclass
class Item:
    text: str
    n: int
    page: int | None
    path: tuple
    section_start: bool            # the item begins a new section (its heading text is in the item)
    kind: str
    overlap: bool = False


def split_text(text: str, limit: int) -> list[str]:
    """Pieces of at most `limit` words cut between sentences (a longer sentence is cut by words)."""
    out, cur, cur_n = [], [], 0
    for sent in re.split(r"(?<=[.!?])\s+", text):
        w = sent.split()
        while len(w) > limit:
            if cur:
                out.append(" ".join(cur)); cur, cur_n = [], 0
            out.append(" ".join(w[:limit])); w = w[limit:]
        if not w:
            continue
        if cur and cur_n + len(w) > limit:
            out.append(" ".join(cur)); cur, cur_n = [], 0
        cur += w
        cur_n += len(w)
    if cur:
        out.append(" ".join(cur))
    return out


def split_table(text: str, limit: int) -> list[str]:
    """Pieces of a table cut between rows, the header (and the separator row) repeated in every piece."""
    lines = text.split("\n")
    head = lines[:2] if len(lines) > 1 and re.fullmatch(r"\|(?:-+\|)+", lines[1]) else lines[:1]
    rows, out, cur = lines[len(head):], [], []
    for row in rows:
        if cur and words("\n".join(head + cur + [row])) > limit:
            out.append("\n".join(head + cur)); cur = []
        cur.append(row)
    if cur:
        out.append("\n".join(head + cur))
    return out or [text]


def to_items(blocks: list[Block], target: int = TARGET, max_words: int = MAX) -> list[Item]:
    """Blocks -> items: headings are glued to the first block below them, oversized blocks are split."""
    items, pending = [], []
    for b in blocks:
        if b.kind == "heading":
            pending.append(b.text)
            continue
        if words(b.text) > max_words:
            pieces = split_table(b.text, target) if b.kind == "table" else split_text(b.text, target)
        else:
            pieces = [b.text]
        for k, piece in enumerate(pieces):
            start = bool(pending) and k == 0
            if start:
                piece = "\n".join(pending) + "\n\n" + piece
                pending = []
            items.append(Item(piece, words(piece), b.page, b.path, start, b.kind))
    return items


def pack(items: list[Item], target: int = TARGET, max_words: int = MAX, min_words: int = MIN,
         overlap_max: int = OVERLAP_MAX) -> list[list[Item]]:
    chunks: list[list[Item]] = []
    buf: list[Item] = []

    def size() -> int:
        return sum(i.n for i in buf)

    def flush(carry: bool):
        nonlocal buf
        if not any(not i.overlap for i in buf):
            buf = []
            return
        chunks.append(buf)
        last = buf[-1]
        buf = [replace(last, overlap=True, section_start=False)] if carry and last.kind == "text" and last.n <= overlap_max else []

    for it in items:
        if buf and it.section_start:
            same_parent = buf[-1].path[:-1] == it.path[:-1]
            if size() >= min_words or not same_parent or size() + it.n > max_words:
                flush(carry=False)
        elif buf and (size() + it.n > max_words or (size() + it.n > target and size() >= min_words)):
            flush(carry=True)
        buf.append(it)
    flush(carry=False)
    return absorb_tiny(chunks, min_words, max_words)


def absorb_tiny(chunks: list[list[Item]], min_words: int, max_words: int) -> list[list[Item]]:
    """A chunk below min_words is appended to the previous chunk of the document when the result is at most max_words
    (also across a parent section: the `sections` field of the chunk then lists both). The first chunk of a document
    is merged forward instead."""
    out: list[list[Item]] = []
    pending: list[Item] = []
    for ch in chunks:
        ch = pending + ch
        pending = []
        own = sum(i.n for i in ch if not i.overlap)
        if own >= min_words:
            out.append(ch)
        elif out and sum(i.n for i in out[-1]) + own <= max_words:
            out[-1] = out[-1] + [i for i in ch if not i.overlap]
        elif not out:
            pending = [replace(i, overlap=False) for i in ch if not i.overlap]
        else:
            out.append(ch)
    if pending:
        out.append(pending)
    return out


def chunk_document(blocks: list[Block], **kw) -> list[dict]:
    """Chunks of one document: dicts with text, n_words, overlap_words, section, section_path, sections, page_start/end."""
    out = []
    for buf in pack(to_items(blocks, kw.get("target", TARGET), kw.get("max_words", MAX)), **kw):
        own = [i for i in buf if not i.overlap]
        text = "\n\n".join(i.text for i in buf)
        secs = []
        for i in own:
            s = " > ".join(i.path)
            if s not in secs:
                secs.append(s)
        pages = [i.page for i in own if i.page is not None]
        out.append({"text": text, "n_words": words(text), "overlap_words": sum(i.n for i in buf if i.overlap),
                    "section": secs[0], "section_path": list(own[0].path), "sections": secs,
                    "page_start": min(pages) if pages else None, "page_end": max(pages) if pages else None})
    return out
