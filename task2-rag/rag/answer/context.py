"""Chunks -> numbered passages for the prompt, within a token budget."""


def page_label(chunk: dict) -> str:
    a, b = chunk.get("page_start"), chunk.get("page_end")
    if a is None:
        return ""
    return f"page {a}" if a == b or b is None else f"pages {a}-{b}"


def version_marks(hits: list[dict]) -> dict[str, str]:
    """doc_id -> "NEWEST VERSION" / "OLDER VERSION" for documents of the hits that share a title but are different documents
    with different dates (versions of one document). The comparison is done here, in code, not by the model. Nothing is
    marked when a document of the group has no date (the year is then used; when it is also missing or equal, no mark)."""
    groups: dict[str, dict[str, dict]] = {}
    for h in hits:
        groups.setdefault(" ".join(h["title"].lower().split()), {})[h["doc_id"]] = h
    marks = {}
    for docs in groups.values():
        if len(docs) < 2:
            continue
        for field in ("date", "year"):
            keys = {d: h.get(field) for d, h in docs.items()}
            if all(k is not None for k in keys.values()):
                keys = {d: str(k)[:4] if field == "year" else str(k) for d, k in keys.items()}
                if len(set(keys.values())) > 1:
                    newest = max(keys.values())
                    marks.update({d: "NEWEST VERSION" if k == newest else "OLDER VERSION" for d, k in keys.items()})
                break
    return marks


def header(chunk: dict, n: int, mark: str | None = None) -> str:
    """`[2] Remote Work Policy (remote_work_policy), version 2.0, effective 2026-01-15, section: 5. Security, page 2`"""
    parts = [f"{chunk['title']} ({chunk['doc_id']})"]
    if chunk.get("version"):
        parts.append(f"version {chunk['version']}")
    if chunk.get("date"):
        parts.append(f"effective {chunk['date']}")
    elif chunk.get("year"):
        parts.append(f"year {chunk['year']}")
    if mark:
        parts.append(mark)
    parts.append(f"section: {chunk['section']}")
    if page_label(chunk):
        parts.append(page_label(chunk))
    return f"[{n}] " + ", ".join(parts)


def build_context(hits: list[dict], budget: int, tokens, mark_versions: bool = False) -> tuple[str, list[dict]]:
    """Take the hits in rank order; a chunk goes in whole or not at all. A chunk that does not fit the remaining budget is
    skipped and a smaller one further down may still fit. Passages are numbered 1..N in the order they are used.
    mark_versions: add NEWEST VERSION / OLDER VERSION to the headers of versions of one document (see version_marks).
    Returns (context text, [{"n", "chunk"}])."""
    marks = version_marks(hits) if mark_versions else {}
    blocks, used, total = [], [], 0
    for h in hits:
        n = len(used) + 1
        block = header(h, n, marks.get(h["doc_id"])) + "\n" + h["text"].strip()
        cost = tokens(block)
        if total + cost > budget:
            continue
        blocks.append(block)
        used.append({"n": n, "chunk": h})
        total += cost
    return "\n\n".join(blocks), used
