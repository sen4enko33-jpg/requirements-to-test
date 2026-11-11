"""Chunks of the whole corpus: rag/data/chunks.jsonl and rag/data/chunks_manifest.json."""
import hashlib
import json
import time
from pathlib import Path

from ..models import EMBED_MODEL
from .blocks import parse_blocks
from .structural import MAX, MAX_TOKENS, MIN, OVERLAP_MAX, TARGET, chunk_document

PKG = Path(__file__).resolve().parent
STRATEGY = "structural-v1"


def code_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(PKG.glob("*.py")):
        if f.name != "cli.py":
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def build(data_dir: Path, out_chunks: Path, out_manifest: Path, tokens=None) -> dict:
    """Chunk every document with the status 'ok' of data_dir/manifest.json (duplicates and failed files are skipped)."""
    data_dir = Path(data_dir)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    records, per_doc = [], {}
    for e in manifest["documents"]:
        if e["status"] != "ok":
            continue
        md = (data_dir / "processed" / f"{e['doc_id']}.md").read_text(encoding="utf-8")
        chunks = chunk_document(parse_blocks(md), tokens=tokens)
        for i, c in enumerate(chunks):
            records.append({
                "chunk_id": f"{e['doc_id']}#{i:04d}", "doc_id": e["doc_id"], "source_file": e["file"], "title": e["title"],
                "section": c["section"], "section_path": c["section_path"], "sections": c["sections"],
                "page_start": c["page_start"], "page_end": c["page_end"], "year": e["year"], "version": e["version"],
                "date": e["date"], "doc_sha256": e["sha256_text"], "sha256": hashlib.sha256(c["text"].encode()).hexdigest(),
                "n_words": c["n_words"], "n_tokens": c["n_tokens"], "overlap_words": c["overlap_words"], "position": i, "n_chunks_in_doc": len(chunks),
                "prev_id": f"{e['doc_id']}#{i - 1:04d}" if i else None,
                "next_id": f"{e['doc_id']}#{i + 1:04d}" if i + 1 < len(chunks) else None, "text": c["text"]})
        sizes = [c["n_words"] for c in chunks]
        per_doc[e["doc_id"]] = {"chunks": len(chunks), "words_mean": round(sum(sizes) / max(len(sizes), 1)),
                                "words_max": max(sizes, default=0), "oversize": sum(1 for s in sizes if s > MAX),
                                "tiny": sum(1 for s in sizes if s < MIN),
                                "over_512_tokens": sum(1 for c in chunks if (c["n_tokens"] or 0) > 512)}
    out_chunks.parent.mkdir(parents=True, exist_ok=True)
    out_chunks.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    summary = {"created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "strategy": STRATEGY, "code_hash": code_hash(),
               "ingestion_code_hash": manifest.get("code_hash"),
               "params": {"target_words": TARGET, "max_words": MAX, "min_words": MIN, "overlap_max_words": OVERLAP_MAX,
                          "max_tokens": MAX_TOKENS if tokens else None, "tokenizer": EMBED_MODEL if tokens else None},
               "n_documents": len(per_doc), "n_chunks": len(records), "documents": per_doc}
    out_manifest.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def build_fixed(data_dir: Path, out_chunks: Path, tokens=None, size: int = 300, overlap: float = 0.15) -> int:
    """The fixed-size baseline in the same record format (only the fields search needs). Not used for answering."""
    from .fixed import chunk_fixed
    data_dir = Path(data_dir)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    n = 0
    with open(out_chunks, "w", encoding="utf-8") as f:
        for e in manifest["documents"]:
            if e["status"] != "ok":
                continue
            md = (data_dir / "processed" / f"{e['doc_id']}.md").read_text(encoding="utf-8")
            for i, c in enumerate(chunk_fixed(parse_blocks(md), size, overlap)):
                rec = {"chunk_id": f"{e['doc_id']}#F{i:04d}", "doc_id": e["doc_id"], "source_file": e["file"], "title": e["title"],
                       "section": c["sections"][0], "sections": c["sections"], "year": e["year"], "version": e["version"],
                       "date": e["date"], "sha256": hashlib.sha256(c["text"].encode()).hexdigest(), "n_words": c["n_words"],
                       "n_tokens": tokens(c["text"]) if tokens else None, "position": i, "text": c["text"]}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    return n
