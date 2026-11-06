"""Structure-aware chunking: chunks follow the sections of a document.

A chunk is made of blocks of one section (or of a few tiny sibling sections), about TARGET words, never more than MAX words
and never more than MAX_TOKENS model tokens (except one unsplittable block). A heading always stays with the text below it.
A long section is cut between paragraphs; the continuation starts with the last paragraph of the previous chunk (the
overlap). Between sections there is no overlap. The token limit is optional: it is used when a `tokens` function
(text -> number of tokens) is given, because code, logs and tables use many more tokens per word than prose.
"""
import re
from dataclasses import dataclass, replace

from .blocks import Block, words

TARGET, MAX, MIN, OVERLAP_MAX = 300, 400, 60, 60
MAX_TOKENS = 480                   # the embedding model reads 512 tokens; the rest is a margin for headings and special tokens


@dataclass
class Item:
    text: str
    n: int                         # words
    page: int | None
    path: tuple
    section_start: bool            # the item begins a new section (its heading text is in the item)
    kind: str
    overlap: bool = False
    t: int = 0                     # tokens (0 when no token function is used)


def _fits(ws: list[str], limit_w: int, limit_t: int | None, tokens) -> bool:
    return len(ws) <= limit_w and (not tokens or tokens(" ".join(ws)) <= limit_t)


def _cut(ws: list[str], limit_w: int, limit_t: int | None, tokens) -> int:
    """How many words from the start of `ws` fit the limits (at least one)."""
    hi = min(len(ws), limit_w)
    if _fits(ws[:hi], limit_w, limit_t, tokens):
        return hi
    lo = 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _fits(ws[:mid], limit_w, limit_t, tokens):
            lo = mid
        else:
            hi = mid - 1
    return lo


def split_text(text: str, limit: int, limit_t: int | None = None, tokens=None) -> list[str]:
    """Pieces of at most `limit` words (and `limit_t` tokens) cut between sentences; a longer sentence is cut by words."""
    out, cur = [], []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        w = sent.split()
        if not w:
            continue
        if not _fits(w, limit, limit_t, tokens):
            if cur:
                out.append(" ".join(cur)); cur = []
            while w and not _fits(w, limit, limit_t, tokens):
                k = _cut(w, limit, limit_t, tokens)
                out.append(" ".join(w[:k])); w = w[k:]
            cur = list(w)
            continue
        if cur and not _fits(cur + w, limit, limit_t, tokens):
            out.append(" ".join(cur)); cur = []
        cur += w
    if cur:
        out.append(" ".join(cur))
    return out


def split_table(text: str, limit: int, limit_t: int | None = None, tokens=None) -> list[str]:
    """Pieces of a table cut between rows, the header (and the separator row) repeated in every piece."""
    lines = text.split("\n")
    head = lines[:2] if len(lines) > 1 and re.fullmatch(r"\|(?:-+\|)+", lines[1]) else lines[:1]
    rows, out, cur = lines[len(head):], [], []

    def fits(parts):
        t = "\n".join(parts)
        return words(t) <= limit and (not tokens or tokens(t) <= limit_t)

    for row in rows:
        if cur and not fits(head + cur + [row]):
            out.append("\n".join(head + cur)); cur = []
        cur.append(row)
    if cur:
        out.append("\n".join(head + cur))
    return out or [text]


def to_items(blocks: list[Block], target: int = TARGET, max_words: int = MAX, tokens=None,
             max_tokens: int = MAX_TOKENS) -> list[Item]:
    """Blocks -> items: headings are glued to the first block below them, oversized blocks are split."""
    items, pending = [], []
    for b in blocks:
        if b.kind == "heading":
            pending.append(b.text)
            continue
        big = words(b.text) > max_words or (tokens and tokens(b.text) > max_tokens)
        if big:
            room = max_tokens - (tokens("\n".join(pending) + "\n\n") if tokens and pending else 0)   # the headings go in front
            pieces = split_table(b.text, target, room, tokens) if b.kind == "table" else split_text(b.text, target, room, tokens)
        else:
            pieces = [b.text]
        for k, piece in enumerate(pieces):
            start = bool(pending) and k == 0
            if start:
                piece = "\n".join(pending) + "\n\n" + piece
                pending = []
            items.append(Item(piece, words(piece), b.page, b.path, start, b.kind, t=tokens(piece) if tokens else 0))
    return items


def pack(items: list[Item], target: int = TARGET, max_words: int = MAX, min_words: int = MIN,
         overlap_max: int = OVERLAP_MAX, max_tokens: int | None = None) -> list[list[Item]]:
    chunks: list[list[Item]] = []
    buf: list[Item] = []
    limit_t = max_tokens if any(i.t for i in items) else None

    def size() -> int:
        return sum(i.n for i in buf)

    def tsize() -> int:
        return sum(i.t for i in buf)

    def too_big(it: Item) -> bool:
        return size() + it.n > max_words or bool(limit_t and tsize() + it.t > limit_t)

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
            if size() >= min_words or not same_parent or too_big(it):
                flush(carry=False)
        elif buf and (too_big(it) or (size() + it.n > target and size() >= min_words)):
            flush(carry=True)
            if buf and limit_t and tsize() + it.t > limit_t:     # the overlap paragraph would not fit with the next item
                buf = []
        buf.append(it)
    flush(carry=False)
    return absorb_tiny(chunks, min_words, max_words, limit_t)


def absorb_tiny(chunks: list[list[Item]], min_words: int, max_words: int, limit_t: int | None = None) -> list[list[Item]]:
    """A chunk below min_words is appended to the previous chunk of the document when the result fits the limits
    (also across a parent section: the `sections` field of the chunk then lists both). The first chunk of a document
    is merged forward instead."""
    out: list[list[Item]] = []
    pending: list[Item] = []
    for ch in chunks:
        ch = pending + ch
        pending = []
        own_items = [i for i in ch if not i.overlap]
        own = sum(i.n for i in own_items)
        fits_prev = bool(out) and sum(i.n for i in out[-1]) + own <= max_words and \
            (not limit_t or sum(i.t for i in out[-1]) + sum(i.t for i in own_items) <= limit_t)
        if own >= min_words:
            out.append(ch)
        elif fits_prev:
            out[-1] = out[-1] + own_items
        elif not out:
            pending = [replace(i, overlap=False) for i in own_items]
        else:
            out.append(ch)
    if pending:
        out.append(pending)
    return out


def chunk_document(blocks: list[Block], target: int = TARGET, max_words: int = MAX, min_words: int = MIN,
                   overlap_max: int = OVERLAP_MAX, tokens=None, max_tokens: int = MAX_TOKENS) -> list[dict]:
    """Chunks of one document: dicts with text, n_words, n_tokens, overlap_words, section, section_path, sections, pages."""
    out = []
    items = to_items(blocks, target, max_words, tokens, max_tokens)
    for buf in pack(items, target, max_words, min_words, overlap_max, max_tokens):
        own = [i for i in buf if not i.overlap]
        text = "\n\n".join(i.text for i in buf)
        secs = []
        for i in own:
            s = " > ".join(i.path)
            if s not in secs:
                secs.append(s)
        pages = [i.page for i in own if i.page is not None]
        out.append({"text": text, "n_words": words(text), "n_tokens": tokens(text) if tokens else None,
                    "overlap_words": sum(i.n for i in buf if i.overlap),
                    "section": secs[0], "section_path": list(own[0].path), "sections": secs,
                    "page_start": min(pages) if pages else None, "page_end": max(pages) if pages else None})
    return out
