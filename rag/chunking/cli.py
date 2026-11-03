"""Chunk the corpus: python -m rag.chunking.cli  ->  rag/data/chunks.jsonl, rag/data/chunks_manifest.json"""
from pathlib import Path

from .pipeline import build

DATA = Path(__file__).resolve().parents[1] / "data"


def main():
    s = build(DATA, DATA / "chunks.jsonl", DATA / "chunks_manifest.json")
    sizes = [d["words_mean"] for d in s["documents"].values()]
    print(f"{s['n_chunks']} chunks from {s['n_documents']} documents (mean of per-document mean size: {sum(sizes)/len(sizes):.0f} words)")
    for d, v in s["documents"].items():
        if v["oversize"] or v["tiny"]:
            print(f"  {d}: {v['chunks']} chunks, oversize {v['oversize']}, tiny {v['tiny']}, max {v['words_max']} words")


if __name__ == "__main__":
    main()
