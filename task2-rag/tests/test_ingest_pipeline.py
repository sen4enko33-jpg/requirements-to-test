"""Checks of duplicate detection, the manifest and the cache of the ingestion pipeline. Run: python tests/test_ingest_pipeline.py
Needs pymupdf, beautifulsoup4, lxml, pyyaml (requirements.txt); no LibreOffice or Tesseract."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf                                              # noqa: E402

from rag.ingest.dedup import find_duplicates, normalize     # noqa: E402
from rag.ingest.pipeline import run                         # noqa: E402

failed = []


def check(name: str, cond: bool):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        failed.append(name)


SENTENCES = [f"The system shall support function number {i} for the operator of the station." for i in range(60)]
PAGE = "<html><head><title>{t}</title></head><body><h1>{t}</h1><h2>1. Scope</h2><p>{body}</p></body></html>"

# --- duplicate detection on plain text
a = "## Scope\n\n" + " ".join(SENTENCES)
texts = {"a": a, "b": a.upper().replace("##", "#"), "c": a + " One more added sentence about reporting.", "d": "## Other\n\n" + " ".join(f"Unrelated sentence {i} about weather." for i in range(60))}
exact, near = find_duplicates(texts)
check("normalisation ignores case, markup and page markers", normalize("<!-- page 1 -->\n\n## Scope, A!") == "scope a")
check("exact duplicate found, the first document is kept", exact == {"b": "a"})
check("a near duplicate (a version) is marked, not dropped", [n["doc_id"] for n in near["c"]] == ["a"] and "c" not in exact)
check("an unrelated document has no duplicates", near["d"] == [])

# --- the pipeline on a temporary corpus
root = Path(tempfile.mkdtemp())
try:
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    (raw / "a.html").write_text(PAGE.format(t="Alpha Spec", body=" ".join(SENTENCES)), encoding="utf-8")
    (raw / "b.html").write_text(PAGE.format(t="Alpha Spec", body=" ".join(SENTENCES)), encoding="utf-8")
    (raw / "c.html").write_text(PAGE.format(t="Alpha Spec v2", body=" ".join(SENTENCES) + " Added sentence about audit logs."), encoding="utf-8")
    (raw / "d.html").write_text(PAGE.format(t="Weather", body=" ".join(f"Unrelated sentence {i} about weather." for i in range(60))), encoding="utf-8")
    pdf = pymupdf.open()
    for _ in range(2):
        pdf.new_page().insert_textbox(pymupdf.Rect(72, 72, 520, 700), " ".join(SENTENCES[:20]), fontsize=11)
    pdf.save(str(raw / "e.pdf"))
    (raw / "broken.pdf").write_bytes(b"this is not a pdf")
    docs = [("a", "html"), ("b", "html"), ("c", "html"), ("d", "html"), ("e", "pdf"), ("broken", "pdf")]
    lines = ["documents:"] + [f"  - doc_id: {n}\n    file: \"{n}.{f}\"\n    format: {f}\n    year: 2026\n    role: test" for n, f in docs]
    (root / "corpus.yaml").write_text("\n".join(lines) + "\n")
    out, man = root / "processed", root / "manifest.json"

    m = run(root, out, man)
    by = {e["doc_id"]: e for e in m["documents"]}
    check("manifest has one entry per corpus document", [e["doc_id"] for e in m["documents"]] == [n for n, _ in docs])
    check("exact duplicate has status 'duplicate' and points to the kept one", by["b"]["status"] == "duplicate" and by["b"]["duplicate_of"] == "a")
    check("near duplicate keeps status 'ok' and lists the other version", by["c"]["status"] == "ok" and by["c"]["near_duplicates"][0]["doc_id"] == "a")
    check("a broken file fails alone, the others are processed", by["broken"]["status"] == "failed" and by["a"]["status"] == "ok" and by["e"]["status"] == "ok")
    check("counts are summed per status", m["counts"] == {"ok": 4, "duplicate": 1, "failed": 1})
    check("hashes are 64 hex characters", all(len(e["sha256_raw"]) == 64 and len(e.get("sha256_text", "x" * 64)) == 64 for e in m["documents"]))
    check("title comes from the first '# ' heading", by["a"]["title"] == "Alpha Spec")
    check("PDF pages are recorded", by["e"]["extraction"]["pages"] == 2)
    check("cleaned Markdown is written for every readable document", all((out / f"{n}.md").exists() for n in "abcde") and not (out / "broken.md").exists())
    check("the manifest on disk equals the returned one", json.loads(man.read_text())["counts"] == m["counts"])

    m2 = run(root, out, man)
    check("second run uses the cache for every document", m2["processed_now"] == 0 and m2["from_cache"] == 6)
    check("duplicates are found again on a cached run", {e["doc_id"]: e["status"] for e in m2["documents"]}["b"] == "duplicate")
    (raw / "d.html").write_text(PAGE.format(t="Weather", body="Completely different text now. " * 40), encoding="utf-8")
    m3 = run(root, out, man)
    check("a changed raw file is processed again, the rest come from the cache", m3["processed_now"] == 1 and m3["from_cache"] == 5)
    check("--ids processes only the listed documents", run(root, out, man, force_ids={"a"})["processed_now"] == 1)
    check("--force processes everything", run(root, out, man, force=True)["processed_now"] == 6)
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"\n{len(failed)} failed" if failed else "\nall checks passed")
sys.exit(1 if failed else 0)
