"""Chunk the corpus: python -m rag.chunking.cli  ->  rag/data/chunks.jsonl, rag/data/chunks_manifest.json"""
from pathlib import Path

from ..models import token_counter
import sys

from .pipeline import build, build_fixed

DATA = Path(__file__).resolve().parents[1] / "data"


def main():
    if "--fixed" in sys.argv:       # the baseline for the retrieval comparison
        n = build_fixed(DATA, DATA / "chunks_fixed.jsonl", tokens=token_counter())
        print(f"{n} fixed-size chunks -> rag/data/chunks_fixed.jsonl")
        return
    s = build(DATA, DATA / "chunks.jsonl", DATA / "chunks_manifest.json", tokens=token_counter())
    sizes = [d["words_mean"] for d in s["documents"].values()]
    print(f"{s['n_chunks']} chunks from {s['n_documents']} documents (mean of per-document mean size: {sum(sizes)/len(sizes):.0f} words)")
    for d, v in s["documents"].items():
        if v["oversize"] or v["tiny"]:
            print(f"  {d}: {v['chunks']} chunks, oversize {v['oversize']}, tiny {v['tiny']}, max {v['words_max']} words")


if __name__ == "__main__":
    main()
