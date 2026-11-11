"""Corpus ingestion: raw files -> cleaned Markdown (processed/) + manifest.json.

Unchanged files are not processed again: an entry is reused when the raw file hash and the hash of the ingestion code
are the same as in the previous manifest (--force / --ids override that).
"""
import hashlib
import json
import re
import time
from importlib import metadata
from pathlib import Path

import yaml

from .clean import clean, doc_version
from .dedup import find_duplicates, text_hash
from .extract import extract
from .extract_pdf import OCR_LANG, ScannedPdfError

PKG = Path(__file__).resolve().parent


def code_hash() -> str:
    """Hash of the ingestion code: a changed extractor or cleaning rule invalidates the cached results."""
    h = hashlib.sha256()
    for f in sorted(PKG.glob("*.py")):
        if f.name not in ("cli.py", "pipeline.py"):
            h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def _tools() -> dict:
    out = {}
    for name in ("pymupdf", "python-docx", "beautifulsoup4", "lxml"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def title_of(md: str, meta: dict) -> str | None:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    if meta.get("title"):
        return meta["title"]
    for unit in re.split(r"\n{2,}", md):
        unit = unit.strip()
        if unit and not unit.startswith(("<!--", "#", "|", "- ")) and len(unit) <= 120:
            return unit
    for line in md.splitlines():
        if line.startswith("#"):
            return line.lstrip("# ").strip()
    return None


def process_one(path: Path, d: dict) -> tuple[dict, str | None]:
    """(manifest entry, cleaned Markdown or None) for one corpus document."""
    entry = {"doc_id": d["doc_id"], "file": d["file"], "format": d["format"], "year": d.get("year"),
             "role": d.get("role"), "sha256_raw": hashlib.sha256(path.read_bytes()).hexdigest(),
             "status": "ok", "error": None, "duplicate_of": None, "near_duplicates": []}
    try:
        raw_md, meta = extract(path)
    except ScannedPdfError as e:
        return {**entry, "status": "skipped_scanned", "error": str(e)}, None
    except Exception as e:                                     # one broken file must not stop the corpus
        return {**entry, "status": "failed", "error": f"{type(e).__name__}: {e}"}, None
    ver = doc_version(raw_md)                                  # before the running headers are removed
    md, stats = clean(raw_md, d["format"])
    warnings = stats.pop("warnings")
    entry.update({"title": title_of(md, meta) or re.sub(r"^\d{4} - ", "", Path(d["file"]).stem), "version": ver["version"], "date": ver["date"],
                  "sha256_text": text_hash(md), "words": stats["words_after"], "chars": len(md),
                  "extraction": meta, "cleaning": stats, "warnings": warnings})
    return entry, md


def run(root: Path, out_dir: Path, manifest_path: Path, force: bool = False, force_ids: set[str] | None = None) -> dict:
    root, out_dir, manifest_path = Path(root), Path(out_dir), Path(manifest_path)
    docs = yaml.safe_load((root / "corpus.yaml").read_text(encoding="utf-8"))["documents"]
    out_dir.mkdir(parents=True, exist_ok=True)
    prev, prev_hash = {}, None
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        prev, prev_hash = {e["doc_id"]: e for e in old["documents"]}, old.get("code_hash")
    chash = code_hash()
    entries, texts, n_new, n_cached = [], {}, 0, 0
    for d in docs:
        path, md_path = root / "data" / "raw" / d["file"], out_dir / f"{d['doc_id']}.md"
        old_e = prev.get(d["doc_id"])
        usable = (not force and d["doc_id"] not in (force_ids or set()) and old_e and prev_hash == chash
                  and old_e["sha256_raw"] == hashlib.sha256(path.read_bytes()).hexdigest()
                  and (old_e["status"] in ("skipped_scanned", "failed") or md_path.exists()))
        if usable:
            entry = {**old_e, "status": "ok" if old_e["status"] == "duplicate" else old_e["status"],
                     "duplicate_of": None, "near_duplicates": []}
            md = md_path.read_text(encoding="utf-8") if entry["status"] == "ok" else None
            n_cached += 1
        else:
            entry, md = process_one(path, d)
            if md is not None:
                md_path.write_text(md, encoding="utf-8")
            n_new += 1
        entries.append(entry)
        if md is not None:
            texts[d["doc_id"]] = md
    exact, near = find_duplicates(texts)
    for e in entries:
        if e["doc_id"] in exact:
            e["status"], e["duplicate_of"] = "duplicate", exact[e["doc_id"]]
        e["near_duplicates"] = near.get(e["doc_id"], [])
    counts = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    manifest = {"created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "code_hash": chash, "ocr_lang": OCR_LANG,
                "tools": _tools(), "n_documents": len(entries), "counts": counts, "documents": entries}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest["processed_now"], manifest["from_cache"] = n_new, n_cached
    return manifest
