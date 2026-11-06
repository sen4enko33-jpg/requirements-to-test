"""Structural vs fixed-size chunking: python -m rag.chunking.compare -> rag/data/chunking_comparison.md
The comparison is a report only; nothing downstream reads it."""
import json
import re
from pathlib import Path

from ..models import token_counter
from .blocks import parse_blocks
from .fixed import chunk_fixed
from .metrics import metrics
from .structural import chunk_document

DATA = Path(__file__).resolve().parents[1] / "data"
EXAMPLES = ["remote_work_policy", "2004_sprat", "2004_grid_bgc", "2006_eirene_sys_15"]
KEYS = [("chunks", "chunks"), ("words_mean", "size mean (words)"), ("words_median", "size median"), ("words_p95", "size p95"),
        ("words_max", "size max"), ("start_mid_sentence_pct", "start mid-sentence, %"),
        ("end_mid_sentence_pct", "end mid-sentence, %"), ("spans_sections_pct", "spans >1 section, %"),
        ("ends_with_heading_pct", "ends with a heading, %")]


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def edge(t, n=140):
    t = norm(t)
    return t if len(t) <= 2 * n + 5 else t[:n] + " [...] " + t[-n:]


def main():
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    docs = [e["doc_id"] for e in manifest["documents"] if e["status"] == "ok"]
    tokens = token_counter()
    allc = {"structural": [], "fixed": []}
    heads, per = set(), {}
    for d in docs:
        bl = parse_blocks((DATA / "processed" / f"{d}.md").read_text(encoding="utf-8"))
        hs = {b.text for b in bl if b.kind == "heading"}
        s, f = chunk_document(bl, tokens=tokens), chunk_fixed(bl)
        for c in f:
            c["n_tokens"] = tokens(c["text"])
        heads |= hs
        per[d] = (s, f, hs)
        allc["structural"] += s
        allc["fixed"] += f
    m = {k: metrics(v, heads) for k, v in allc.items()}
    out = ["# Chunking comparison: structural-v1 vs fixed size", "",
           f"Corpus: {len(docs)} documents. Fixed size: windows of 300 words, 15% overlap, no structure. "
           "Structural: sections, target 300 / max 400 / min 60 words (see README). Metrics are heuristics on the chunk text "
           "and are computed in the same way for both strategies.", "",
           "| metric | structural-v1 | fixed 300 |", "|---|---|---|"]
    out += [f"| {label} | {m['structural'][k]} | {m['fixed'][k]} |" for k, label in KEYS]
    for name, fn in (("chunks over 512 tokens (cut by the embedding model)", lambda c: c["n_tokens"] > 512),):
        out.append(f"| {name} | {sum(fn(c) for c in allc['structural'])} | {sum(fn(c) for c in allc['fixed'])} |")
    lost = lambda cs: round(100 * sum(max(c["n_tokens"] - 512, 0) for c in cs) / sum(c["n_tokens"] for c in cs), 1)
    out.append(f"| text beyond 512 tokens, % | {lost(allc['structural'])} | {lost(allc['fixed'])} |")
    out += ["", "'Spans >1 section' is intended for the structural chunks (a tiny section is attached to its neighbour); for fixed "
            "chunks it shows how often a window mixes unrelated sections. 'Ends with a heading' is a string match: a line "
            "that repeats a heading text (for example a running header left in the text) is counted too.", ""]
    for d in EXAMPLES:
        s, f, hs = per[d]
        ms, mf = metrics(s, hs), metrics(f, hs)
        out += [f"## {d}", "", f"structural: {ms['chunks']} chunks (mean {ms['words_mean']} words, mid-sentence start/end "
                f"{ms['start_mid_sentence_pct']}% / {ms['end_mid_sentence_pct']}%); fixed: {mf['chunks']} chunks (mean {mf['words_mean']}, "
                f"{mf['start_mid_sentence_pct']}% / {mf['end_mid_sentence_pct']}%).", ""]
        bad = next((c for c in f[1:] if metrics([c], hs)["start_mid_sentence_pct"] or metrics([c], hs)["end_mid_sentence_pct"]), f[min(1, len(f) - 1)])
        key = norm(bad["text"]).split(" ")[:6]
        match = next((c for c in s if " ".join(key) in norm(c["text"])), None)
        out += ["Fixed chunk that cuts the text:", "", "> " + edge(bad["text"]), ""]
        if match:
            out += [f"Structural chunk with the same beginning (section: {match['section']}):", "", "> " + edge(match["text"]), ""]
        else:
            out += ["(The structural chunking starts at a section boundary here, so there is no chunk with the same beginning.)", ""]
    (DATA / "chunking_comparison.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:20]))


if __name__ == "__main__":
    main()
