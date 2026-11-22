"""Access to the corpus of task 2: the chunks, the document manifest and the search (Chroma + BM25 + reranker).

Nothing is copied: the package `rag` is imported from ../task2-rag (or TASK2_RAG_DIR), and the index built there
(`python -m rag.retrieval.build` in task2-rag) is used as it is. The search models load lazily on the first search;
call `warm_up()` before a request so that the loading does not count against the timeout of a tool call."""
from __future__ import annotations

import json
import os
import sys
from functools import cached_property
from pathlib import Path

TASK2 = Path(os.environ.get("TASK2_RAG_DIR", Path(__file__).resolve().parents[2] / "task2-rag")).resolve()
DATA = TASK2 / "rag" / "data"


def _import_rag():
    if str(TASK2) not in sys.path:
        sys.path.insert(0, str(TASK2))


class Corpus:
    """chunks: chunk dicts of chunks.jsonl; documents: the `documents` of manifest.json; retriever: object with
    .search(query, k, mode, filters) (the real one is created on first use). Tests pass small fakes."""

    def __init__(self, chunks: list[dict] | None = None, documents: list[dict] | None = None, retriever=None):
        self._chunks, self._documents, self._retriever = chunks, documents, retriever

    @cached_property
    def chunks(self) -> dict[str, dict]:
        rows = self._chunks
        if rows is None:
            rows = [json.loads(l) for l in (DATA / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        return {c["chunk_id"]: c for c in rows}

    @cached_property
    def documents(self) -> dict[str, dict]:
        docs = self._documents
        if docs is None:
            docs = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))["documents"]
        # duplicates are not chunked, so they cannot be searched or cited
        return {d["doc_id"]: d for d in docs if d.get("status", "ok") == "ok"}

    @property
    def retriever(self):
        if self._retriever is None:
            _import_rag()
            from rag.retrieval.factory import make_retriever
            self._retriever = make_retriever("structural")
        return self._retriever

    def warm_up(self) -> None:
        """Load the chunks, the manifest, the embedding model and the reranker, and run one search."""
        self.chunks, self.documents
        self.retriever.search("warm up", 1, "hybrid_rerank", None)


def version_marks(hits: list[dict]) -> dict[str, str]:
    """doc_id -> NEWEST VERSION / OLDER VERSION for versions of one document among the hits (the code of task 2)."""
    _import_rag()
    from rag.answer.context import version_marks as marks
    return marks(hits)


def page_label(chunk: dict) -> str:
    _import_rag()
    from rag.answer.context import page_label as label
    return label(chunk)


def min_score() -> float | None:
    """The reranker score below which a hit is not relevant (MIN_SCORE of task 2, chosen on its dev questions)."""
    _import_rag()
    from rag.answer import settings
    return settings.MIN_SCORE
