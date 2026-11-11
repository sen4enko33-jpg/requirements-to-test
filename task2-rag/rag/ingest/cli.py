"""Ingest the corpus of rag/corpus.yaml: python -m rag.ingest.cli [--force] [--ids a b]

Writes rag/data/processed/<doc_id>.md (cleaned Markdown) and rag/data/manifest.json.
"""
import argparse
from pathlib import Path

from .pipeline import run

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="process every document again")
    ap.add_argument("--ids", nargs="*", default=[], help="process only these documents again (the rest come from the cache)")
    ap.add_argument("--out", default=str(ROOT / "data" / "processed"))
    ap.add_argument("--manifest", default=str(ROOT / "data" / "manifest.json"))
    args = ap.parse_args()
    m = run(ROOT, Path(args.out), Path(args.manifest), force=args.force, force_ids=set(args.ids))
    print(f"{m['n_documents']} documents: {m['counts']}  (processed now: {m['processed_now']}, from cache: {m['from_cache']})")
    for e in m["documents"]:
        warnings = e.get("warnings") or []
        if e["status"] != "ok" or warnings:
            print(f"  {e['doc_id']}: {e['status']} {e['duplicate_of'] or e['error'] or ''} {warnings or ''}")
    for e in m["documents"]:
        for n in e["near_duplicates"]:
            if e["doc_id"] < n["doc_id"]:
                print(f"  near duplicates: {e['doc_id']} ~ {n['doc_id']} (jaccard {n['jaccard']}, containment {n['containment']})")
    print(f"manifest: {args.manifest}")


if __name__ == "__main__":
    main()
