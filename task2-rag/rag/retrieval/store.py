"""Chroma collection with the chunk embeddings (cosine distance)."""
import hashlib
import json
import time
from pathlib import Path

import chromadb

META_FIELDS = ("doc_id", "title", "year", "version", "date", "source_file", "section", "position", "n_words")


def load_chunks(path: Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def chunks_sha(chunks: list[dict]) -> str:
    return hashlib.sha256("".join(c["chunk_id"] + c["sha256"] for c in chunks).encode()).hexdigest()[:16]


def _where(filters: dict | None):
    parts = [{k: {"$in": list(v)}} if isinstance(v, (list, tuple, set, frozenset)) else {k: v} for k, v in (filters or {}).items()]
    return None if not parts else parts[0] if len(parts) == 1 else {"$and": parts}


class Store:
    def __init__(self, client, name: str):
        self.client, self.name = client, name
        self.collection = client.get_collection(name)

    @classmethod
    def ensure(cls, client, name: str, chunks: list[dict], embed_docs, model: str = "", batch: int = 64,
               deadline: float | None = None) -> "Store":
        """Open the collection, or (re)build it when it is missing or was built from other chunks or another model.
        An interrupted build is resumed: only the missing chunks are embedded. `deadline` (time.time() value) stops
        the build early; `is_complete` tells whether the collection holds every chunk."""
        sha = chunks_sha(chunks) + "|" + model
        col = None
        try:
            col = client.get_collection(name)
            if (col.metadata or {}).get("source") != sha:
                client.delete_collection(name)
                col = None
        except Exception:
            col = None
        if col is None:
            col = client.create_collection(name, metadata={"hnsw:space": "cosine", "source": sha})
        have = set(col.get(include=[])["ids"]) if col.count() else set()
        todo = [c for c in chunks if c["chunk_id"] not in have]
        for i in range(0, len(todo), batch):
            if deadline is not None and time.time() > deadline:
                break
            part = todo[i:i + batch]
            col.add(ids=[c["chunk_id"] for c in part], embeddings=embed_docs([c["text"] for c in part]),
                    documents=[c["text"] for c in part],
                    metadatas=[{k: c[k] for k in META_FIELDS if c.get(k) is not None} for c in part])
        store = cls(client, name)
        store.expected = len(chunks)
        return store

    @property
    def is_complete(self) -> bool:
        return self.collection.count() == getattr(self, "expected", -1)

    def query(self, vector, n: int, filters: dict | None = None) -> list[tuple[str, float]]:
        """(chunk_id, similarity) of the n nearest chunks that pass the filters, best first."""
        n = min(n, self.collection.count())
        if n <= 0:
            return []
        r = self.collection.query(query_embeddings=[list(map(float, vector))], n_results=n, where=_where(filters),
                                  include=["distances"])
        pairs = list(zip(r["ids"][0], r["distances"][0]))
        return [(i, 1.0 - d) for i, d in sorted(pairs, key=lambda p: (p[1], p[0]))]
