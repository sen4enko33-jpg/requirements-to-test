"""Build the Chroma index: python -m rag.retrieval.build [--fixed] [--max-seconds=N]
Embeds rag/data/chunks.jsonl (or chunks_fixed.jsonl) into the collection chunks_structural (chunks_fixed) of rag/data/chroma.
A collection that is up to date (same chunks, same model) is reused."""
import os
import sys
import time
from pathlib import Path

import chromadb

from ..models import EMBED_MODEL, embed_fns
from .store import Store, load_chunks

DATA = Path(__file__).resolve().parents[1] / "data"
CHROMA = Path(os.environ.get("RAG_CHROMA_DIR", DATA / "chroma"))   # SQLite needs a normal local disk (not a network mount)


def client():
    return chromadb.PersistentClient(path=str(CHROMA))


def open_store(name: str, chunks: list[dict], embed_docs, deadline: float | None = None) -> Store:
    return Store.ensure(client(), name, chunks, embed_docs, model=EMBED_MODEL, deadline=deadline)


def main():
    fixed = "--fixed" in sys.argv
    name, path = ("chunks_fixed", DATA / "chunks_fixed.jsonl") if fixed else ("chunks_structural", DATA / "chunks.jsonl")
    chunks = load_chunks(path)
    embed_docs, _ = embed_fns()
    t = time.time()
    limit = next((float(a.split("=")[1]) for a in sys.argv if a.startswith("--max-seconds=")), None)   # for short-lived shells
    store = open_store(name, chunks, embed_docs, deadline=t + limit if limit else None)
    state = "complete" if store.is_complete else f"INCOMPLETE ({store.collection.count()} of {store.expected}), run it again"
    print(f"{name}: {state}; {time.time() - t:.0f} s -> {CHROMA}")


if __name__ == "__main__":
    main()
