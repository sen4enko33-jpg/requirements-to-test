"""Checks of the chunking (no network, no models): python tests/test_chunking.py"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.chunking.blocks import parse_blocks, words
from rag.chunking.fixed import chunk_fixed
from rag.chunking.metrics import ends_mid_sentence, metrics, starts_mid_sentence
from rag.chunking.pipeline import build
from rag.chunking.structural import MAX, chunk_document, split_table, split_text

FAILED = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILED.append(name)


def para(n, tag="w"):
    """A paragraph of n words made of sentences of 10 words."""
    ws = [f"{tag}{i}" for i in range(n)]
    return " ".join(" ".join(ws[i:i + 10]) + "." for i in range(0, n, 10))


def doc(*units):
    return "\n\n".join(units)


# --- parsing
md = doc("# Title", "<!-- page 1 -->", "## A", "text a", "<!-- page 2 -->", "### A1", "text a1", "| h | h2 |\n|---|---|\n| 1 | 2 |")
bl = parse_blocks(md)
check("parse: page markers are not blocks", all("<!--" not in b.text for b in bl))
check("parse: heading path", [b.path for b in bl if b.text == "text a1"] == [("Title", "A", "A1")])
check("parse: page of a block", [b.page for b in bl if b.text == "text a1"] == [2])
check("parse: table block", [b.kind for b in bl][-1] == "table")

# --- structural
md = doc("# T", "## S1", para(250), para(250), para(250), "## S2", para(100))
ch = chunk_document(parse_blocks(md))
check("sizes: no chunk above MAX", all(c["n_words"] <= MAX for c in ch))
body = " ".join(c["text"] for c in ch)
check("no text lost", all(f"w{i}" in body for i in range(250)))
check("section starts a new chunk", ch[-1]["section"].endswith("S2") and not any("S2" in c["text"] for c in ch[:-1]))
check("no overlap across sections", ch[-1]["overlap_words"] == 0)
check("overlap on continuation", any(c["overlap_words"] > 0 for c in ch[1:]) or all(words(para(250)) > 60 for _ in [0]))

# heading is never last, and always with its text
md = doc("# T", "## A", para(280), "## B", "text of b is here and long enough.")
ch = chunk_document(parse_blocks(md))
check("heading not at the end of a chunk", all(c["text"].rstrip().split("\n")[-1] not in ("## A", "## B", "A", "B") for c in ch))
check("heading glued to its text", any(c["text"].startswith("B\n\ntext of b") or "B\n\ntext of b" in c["text"] for c in ch))

# tiny siblings merged
md = doc("# T", "## P1", "### a", "short one.", "### b", "short two.", "## P2", "### c", para(100))
ch = chunk_document(parse_blocks(md))
check("tiny siblings merged", any("short one." in c["text"] and "short two." in c["text"] for c in ch))

# page range
md = doc("# T", "<!-- page 3 -->", "## A", para(250), "<!-- page 4 -->", para(250))
ch = chunk_document(parse_blocks(md))
check("pages", ch[0]["page_start"] == 3 and max(c["page_end"] for c in ch) == 4)

# oversized pieces
check("sentence hard split", all(len(p.split()) <= 50 for p in split_text("word " * 130 + ".", 50)))
rows = "\n".join(f"| r{i} | v{i} |" for i in range(80))
tb = "| name | value |\n|---|---|\n" + rows
parts = split_table(tb, 100)
check("table split with header repeated", len(parts) > 1 and all(p.startswith("| name | value |\n|---|---|") for p in parts))
check("table rows complete", sum(p.count("| r") for p in parts) == 80)
ch = chunk_document(parse_blocks(doc("# T", "## A", tb)))
check("table chunks within MAX", all(c["n_words"] <= MAX for c in ch))

# tiny chunks are absorbed by the previous chunk (also across parents) when the result fits
md = doc("# T", "## P1", para(200), "## P2", "tiny tail section.")
ch = chunk_document(parse_blocks(md))
check("tiny chunk absorbed by the previous one", len(ch) == 1 and len(ch[0]["sections"]) == 2)
md = doc("# T", "## P1", para(398), "## P2", "tiny tail section.")
ch = chunk_document(parse_blocks(md))
check("tiny chunk stays separate when the merge would exceed MAX", len(ch) == 2 and ch[-1]["n_words"] < 60)
md = doc("# T", "tiny title page.", "## P1", para(200))
ch = chunk_document(parse_blocks(md))
check("tiny first chunk merged forward", len(ch) == 1 and ch[0]["text"].startswith("T"))

# determinism
md = doc("# T", "## S", para(500))
check("deterministic", chunk_document(parse_blocks(md)) == chunk_document(parse_blocks(md)))

# --- fixed
bl = parse_blocks(doc("# T", para(1000)))
fx = chunk_fixed(bl, 300, 0.15)
check("fixed: windows <= size", all(c["n_words"] <= 300 for c in fx))
check("fixed: covers everything", all(f"w{i}" in " ".join(c["text"] for c in fx) for i in range(1000)))
check("fixed: overlap ~15%", len(set(fx[0]["text"].split()) & set(fx[1]["text"].split())) >= 40)

# --- metrics
check("metrics: mid-sentence start", starts_mid_sentence("and then it") and not starts_mid_sentence("## Title"))
check("metrics: mid-sentence end", ends_mid_sentence("this line goes on and on without any end at all") and not ends_mid_sentence("A short label"))
m = metrics(ch, {"T"})
check("metrics: keys", {"chunks", "words_p95", "spans_sections_pct", "ends_with_heading_pct"} <= set(m))

# --- pipeline
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "processed").mkdir()
    (d / "processed" / "a.md").write_text(doc("# Doc A", "## One", para(250), para(250), "## Two", para(80)), encoding="utf-8")
    (d / "processed" / "b.md").write_text(doc("# Doc B", "## X", para(120)), encoding="utf-8")
    (d / "processed" / "c.md").write_text(doc("# Doc C", para(120)), encoding="utf-8")
    ent = lambda i, st: {"doc_id": i, "file": f"{i}.pdf", "title": f"Doc {i}", "year": 2020, "version": "1.0", "date": None,
                         "sha256_text": "h" + i, "status": st}
    (d / "manifest.json").write_text(json.dumps({"code_hash": "x", "documents": [ent("a", "ok"), ent("b", "ok"), ent("c", "duplicate")]}))
    s = build(d, d / "chunks.jsonl", d / "chunks_manifest.json")
    rec = [json.loads(l) for l in (d / "chunks.jsonl").read_text().splitlines()]
    check("pipeline: duplicates skipped", {r["doc_id"] for r in rec} == {"a", "b"})
    check("pipeline: unique ids", len({r["chunk_id"] for r in rec}) == len(rec))
    check("pipeline: required metadata", all(all(r.get(k) is not None for k in ("source_file", "title", "section", "doc_sha256", "sha256", "text")) for r in rec))
    a = [r for r in rec if r["doc_id"] == "a"]
    check("pipeline: prev/next links", a[0]["prev_id"] is None and a[-1]["next_id"] is None and a[1]["prev_id"] == a[0]["chunk_id"])
    check("pipeline: positions", [r["position"] for r in a] == list(range(len(a))) and a[0]["n_chunks_in_doc"] == len(a))
    check("pipeline: manifest counts", s["n_chunks"] == len(rec) and s["n_documents"] == 2)

print("\n%d failed" % len(FAILED) if FAILED else "\nall ok")
sys.exit(1 if FAILED else 0)
