"""Chunks -> numbered passages for the prompt, within a token budget."""


def page_label(chunk: dict) -> str:
    a, b = chunk.get("page_start"), chunk.get("page_end")
    if a is None:
        return ""
    return f"page {a}" if a == b or b is None else f"pages {a}-{b}"


def header(chunk: dict, n: int) -> str:
    """`[2] Remote Work Policy (remote_work_policy), version 2.0, effective 2026-01-15, section: 5. Security, page 2`"""
    parts = [f"{chunk['title']} ({chunk['doc_id']})"]
    if chunk.get("version"):
        parts.append(f"version {chunk['version']}")
    if chunk.get("date"):
        parts.append(f"effective {chunk['date']}")
    elif chunk.get("year"):
        parts.append(f"year {chunk['year']}")
    parts.append(f"section: {chunk['section']}")
    if page_label(chunk):
        parts.append(page_label(chunk))
    return f"[{n}] " + ", ".join(parts)


def build_context(hits: list[dict], budget: int, tokens) -> tuple[str, list[dict]]:
    """Take the hits in rank order; a chunk goes in whole or not at all. A chunk that does not fit the remaining budget is
    skipped and a smaller one further down may still fit. Passages are numbered 1..N in the order they are used.
    Returns (context text, [{"n", "chunk"}])."""
    blocks, used, total = [], [], 0
    for h in hits:
        n = len(used) + 1
        block = header(h, n) + "\n" + h["text"].strip()
        cost = tokens(block)
        if total + cost > budget:
            continue
        blocks.append(block)
        used.append({"n": n, "chunk": h})
        total += cost
    return "\n\n".join(blocks), used
