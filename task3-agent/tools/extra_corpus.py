"""Documents that task 3 adds to the corpus of task 2 without changing task 2 (step 3.1): corpus_extra/<doc_id>.md.

They are pages of an internal wiki with problems a real corpus has: an instruction for the model hidden in the text
(prompt injection). The agent must treat them as data like any other document: never follow them, never change anything
because of them.

A file is Markdown with a small front matter (title, year, date, source_file); every "## " section is one chunk, with the
fields of the chunks of task 2 (rag/data/chunks.jsonl), so search, citations and get_passage work the same way.

The search of task 2 keeps its Chroma index for its own chunks; the vectors of these few chunks are kept in memory
(MemoryStore) and both stores answer one query together (CombinedStore). BM25 and the reranker see all chunks."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import yaml

EXTRA_DIR = Path(__file__).resolve().parents[1] / "corpus_extra"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_document(path: Path) -> tuple[dict, list[dict]]:
    """-> (a manifest row, the chunks) of one corpus_extra file."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path.name}: needs a front matter (---, title, year, date, source_file, ---)")
    head, body = raw[4:].split("\n---\n", 1)
    meta = yaml.safe_load(head) or {}
    doc_id = path.stem
    body = body.strip()
    if not body.startswith("## "):
        raise ValueError(f"{path.name}: the text must start with a '## ' section")
    sections = []
    for part in ("\n" + body).split("\n## "):
        part = part.strip()
        if not part:
            continue
        heading, _, text = part.partition("\n")
        sections.append((heading.strip(), text.strip()))
    title = meta["title"]
    date = str(meta["date"]) if meta.get("date") else None
    chunks = []
    for i, (heading, text) in enumerate(sections):
        full = f"{heading}\n\n{text}"
        section = f"{title} > {heading}"
        chunks.append({
            "chunk_id": f"{doc_id}#{i:04d}", "doc_id": doc_id, "source_file": meta.get("source_file", path.name),
            "title": title, "section": section, "section_path": [title, heading], "sections": [section],
            "page_start": None, "page_end": None, "year": meta.get("year"), "version": meta.get("version"), "date": date,
            "doc_sha256": _sha(raw), "sha256": _sha(full), "n_words": len(full.split()), "n_tokens": None,
            "overlap_words": 0, "position": i, "n_chunks_in_doc": len(sections),
            "prev_id": f"{doc_id}#{i - 1:04d}" if i else None,
            "next_id": f"{doc_id}#{i + 1:04d}" if i + 1 < len(sections) else None, "text": full})
    doc = {"doc_id": doc_id, "file": path.name, "format": "md", "year": meta.get("year"), "role": "extra_wiki_page",
           "status": "ok", "duplicate_of": None, "near_duplicates": [], "title": title, "version": meta.get("version"),
           "date": date, "words": sum(c["n_words"] for c in chunks), "source": "task3-agent/corpus_extra"}
    return doc, chunks


def load_extra(directory: Path = EXTRA_DIR) -> tuple[list[dict], list[dict]]:
    """-> (manifest rows, chunks) of every corpus_extra/*.md, sorted by file name; nothing when the folder is missing."""
    docs, chunks = [], []
    for path in sorted(Path(directory).glob("*.md")):
        d, c = load_document(path)
        docs.append(d)
        chunks += c
    return docs, chunks


def _matches(meta: dict, filters: dict | None) -> bool:
    for key, want in (filters or {}).items():
        have = meta.get(key)
        if not (have in want if isinstance(want, (list, tuple, set, frozenset)) else have == want):
            return False
    return True


class MemoryStore:
    """The interface of task 2's Store.query for a few chunks embedded at start (cosine similarity, best first)."""

    def __init__(self, chunks: list[dict], embed_docs):
        self.chunks = chunks
        self.vectors = embed_docs([c["text"] for c in chunks]) if chunks else []

    def query(self, vector, n: int, filters: dict | None = None) -> list[tuple[str, float]]:
        q = list(map(float, vector))
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        out = []
        for c, v in zip(self.chunks, self.vectors):
            if _matches(c, filters):
                vn = math.sqrt(sum(x * x for x in v)) or 1.0
                out.append((c["chunk_id"], sum(a * b for a, b in zip(q, v)) / (qn * vn)))
        return sorted(out, key=lambda p: (-p[1], p[0]))[:max(n, 0)]


class CombinedStore:
    """Several stores answer one query: the n most similar chunks of all of them."""

    def __init__(self, *stores):
        self.stores = stores

    def query(self, vector, n: int, filters: dict | None = None) -> list[tuple[str, float]]:
        hits = [h for s in self.stores for h in s.query(vector, n, filters)]
        return sorted(hits, key=lambda p: (-p[1], p[0]))[:n]
